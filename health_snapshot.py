"""Bounded, single-flight health sampling. Never turn old evidence into fresh success."""

from __future__ import annotations

import copy
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone


# Reuse a bounded pool. Slow reads cannot create a new pool per HTTP request.
_read_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="source-health")


def collect_reads(reads, *, timeout=7.0):
    """Return completed independent reads and explicit failures by the deadline.

    Late results never mutate the returned snapshot. Queued work is cancelled;
    running I/O retains its own socket timeout. Avoid the executor context
    manager, which would wait for late I/O when leaving this function.
    """
    futures = {name: _read_pool.submit(read) for name, read in reads.items()}
    done, _ = wait(futures.values(), timeout=timeout)
    values, errors = {}, []
    for name, future in futures.items():
        if future not in done:
            future.cancel()
            errors.append(name + ":DeadlineExceeded")
            continue
        try:
            values[name] = future.result()
        except Exception as error:
            # Exception messages can contain private paths or upstream bodies.
            errors.append(name + ":" + type(error).__name__)
    return values, errors


class HealthSnapshot:
    def __init__(self, cache, *, max_age=60.0, response_timeout=8.0):
        self.cache = cache
        self.max_age = max_age
        self.response_timeout = response_timeout
        self.lock = threading.Lock()
        self.refresh = None
        self.last_error = None
        self.failed_at = 0.0

    def _run(self, builder, finished):
        try:
            payload = builder()
            if not isinstance(payload, dict):
                raise ValueError("health builder must return a snapshot")
            with self.lock:
                self.cache.update(at=time.monotonic(), payload=payload)
                self.last_error = None
        except Exception as error:
            with self.lock:
                self.last_error = "health:" + type(error).__name__
                self.failed_at = time.monotonic()
        finally:
            with self.lock:
                self.refresh = None
                finished.set()

    def _response(self):
        payload = copy.deepcopy(self.cache.get("payload") or {"sources": [], "errors": []})
        sampled = self.cache.get("at", 0.0)
        age = max(0.0, time.monotonic() - sampled) if sampled else None
        fresh = age is not None and age < self.max_age and self.last_error is None
        payload["sample_age_seconds"] = round(age, 3) if age is not None else None
        payload["served_at"] = datetime.now(timezone.utc).isoformat()
        payload["cache_status"] = "fresh" if fresh else "stale" if sampled else "unavailable"
        if not fresh:
            errors = payload.setdefault("errors", [])
            reason = self.last_error or "health:RefreshInProgress"
            if reason not in errors:
                errors.append(reason)
            for source in payload.get("sources", []):
                source["last_known_status"] = source.get("status")
                source["status"] = "unavailable"
                source["detail"] = "Current health sample unavailable. Last observation: " + str(source.get("detail") or "unknown")
        return payload

    def get(self, builder):
        with self.lock:
            at = self.cache.get("at", 0.0)
            if self.cache.get("payload") is not None and time.monotonic() - at < self.max_age and self.last_error is None:
                return self._response()
            # A broken builder gets a short backoff, not one new thread per caller.
            if self.last_error and time.monotonic() - self.failed_at < 5:
                return self._response()
            if self.refresh is None:
                self.refresh = threading.Event()
                threading.Thread(target=self._run, args=(builder, self.refresh), daemon=True,
                                 name="health-refresh").start()
            finished = self.refresh
        finished.wait(self.response_timeout)
        with self.lock:
            return self._response()
