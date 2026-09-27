#!/usr/bin/env python3
"""Build, persist, and mirror durable Acclaim collector run receipts.

The local outbox is written before the Supabase request.  A failed network write
therefore makes the collector fail closed without losing the receipt; the next
invocation can replay pending receipts with the ``flush`` command.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import tempfile
import urllib.request
import uuid
from pathlib import Path


STATUSES = {"ok", "empty", "source_wait", "failed"}
TABLE = "broward_clerk_preliminary_run"
RECEIPT_FIELDS = {
    "run_id",
    "collector",
    "status",
    "started_at",
    "completed_at",
    "observed_at",
    "attempted_from",
    "attempted_through",
    "event_through",
    "verified_through",
    "dates_attempted",
    "rows_observed",
    "rows_new",
    "reason",
    "outcomes",
}


def _timestamp(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def _date(value: str | None) -> dt.date | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("date must be an ISO string")
    return dt.date.fromisoformat(value)


def validate_outcome(outcome: dict) -> dict:
    if not isinstance(outcome, dict):
        raise ValueError("outcome must be an object")
    target_date = _date(str(outcome.get("target_date") or ""))
    status = str(outcome.get("status") or "")
    if status not in STATUSES:
        raise ValueError("invalid outcome status")
    observed_at = _timestamp(str(outcome.get("observed_at") or ""))
    pages = int(outcome.get("pages", 0))
    rows_observed = int(outcome.get("rows_observed", 0))
    rows_new = int(outcome.get("rows_new", 0))
    if min(pages, rows_observed, rows_new) < 0 or rows_new > rows_observed:
        raise ValueError("invalid outcome counts")
    reason = str(outcome.get("reason") or "").strip() or None
    return {
        "target_date": target_date.isoformat(),
        "status": status,
        "pages": pages,
        "rows_observed": rows_observed,
        "rows_new": rows_new,
        "observed_at": observed_at.isoformat(),
        "reason": reason,
    }


def load_outcomes(path: Path) -> list[dict]:
    if not path.exists():
        return []
    outcomes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            outcomes.append(validate_outcome(json.loads(line)))
    return outcomes


def append_outcome(path: Path, outcome: dict) -> None:
    normalized = validate_outcome(outcome)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalized, sort_keys=True, separators=(",", ":")))
        handle.write("\n")


def event_through_from_state(path: Path) -> str | None:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    explicit = state.get("last_event_date")
    if explicit:
        return _date(str(explicit)).isoformat()
    event_dates = [
        date_text
        for date_text, value in (state.get("dates") or {}).items()
        if int(value.get("found") or 0) > 0 and value.get("status") == "done"
    ]
    return max(event_dates) if event_dates else None


def aggregate_status(outcomes: list[dict], forced_status: str | None = None) -> str:
    if forced_status:
        if forced_status not in STATUSES:
            raise ValueError("invalid run status")
        return forced_status
    statuses = {outcome["status"] for outcome in outcomes}
    if "failed" in statuses:
        return "failed"
    if "source_wait" in statuses:
        return "source_wait"
    if outcomes and statuses == {"empty"}:
        return "empty"
    return "ok"


def validate_receipt(receipt: dict) -> dict:
    if not isinstance(receipt, dict):
        raise ValueError("receipt must be an object")
    if set(receipt) != RECEIPT_FIELDS:
        raise ValueError("receipt fields do not match the evidence contract")
    canonical = dict(receipt)
    canonical["run_id"] = str(uuid.UUID(str(receipt["run_id"])))
    if receipt.get("collector") != "acclaim-mac-launchagent":
        raise ValueError("invalid collector identity")
    if receipt.get("status") not in STATUSES:
        raise ValueError("invalid run status")
    started = _timestamp(str(receipt["started_at"]))
    completed = _timestamp(str(receipt["completed_at"]))
    observed = _timestamp(str(receipt["observed_at"]))
    if not started <= observed <= completed:
        raise ValueError("receipt timestamps are out of order")
    raw_outcomes = receipt.get("outcomes")
    if not isinstance(raw_outcomes, list):
        raise ValueError("receipt outcomes must be an array")
    outcomes = [validate_outcome(value) for value in raw_outcomes]
    attempted = sorted(outcome["target_date"] for outcome in outcomes)
    expected_observed = max(
        (_timestamp(outcome["observed_at"]) for outcome in outcomes),
        default=completed,
    )
    if observed != expected_observed:
        raise ValueError("receipt observed_at does not bind to its outcomes")
    expected_from = attempted[0] if attempted else None
    expected_through = attempted[-1] if attempted else None
    if receipt.get("attempted_from") != expected_from or receipt.get(
        "attempted_through"
    ) != expected_through:
        raise ValueError("receipt attempted range does not bind to its outcomes")
    dates_attempted = int(receipt.get("dates_attempted", -1))
    rows_observed = int(receipt.get("rows_observed", -1))
    rows_new = int(receipt.get("rows_new", -1))
    if dates_attempted != len(outcomes):
        raise ValueError("receipt date count does not bind to its outcomes")
    if rows_observed != sum(value["rows_observed"] for value in outcomes):
        raise ValueError("receipt observed-row count does not bind to its outcomes")
    if rows_new != sum(value["rows_new"] for value in outcomes):
        raise ValueError("receipt new-row count does not bind to its outcomes")
    event_date = _date(receipt.get("event_through"))
    attempted_through = _date(expected_through)
    _date(receipt.get("verified_through"))
    if event_date and attempted_through and event_date > attempted_through:
        raise ValueError("event_through exceeds attempted_through")
    reason = receipt.get("reason")
    if reason is not None and (not isinstance(reason, str) or len(reason) > 1000):
        raise ValueError("invalid receipt reason")
    canonical.update(
        {
            "started_at": started.isoformat(),
            "completed_at": completed.isoformat(),
            "observed_at": observed.isoformat(),
            "dates_attempted": dates_attempted,
            "rows_observed": rows_observed,
            "rows_new": rows_new,
            "outcomes": outcomes,
        }
    )
    return canonical


def build_receipt(
    *,
    run_id: str,
    started_at: str,
    completed_at: str,
    verified_through: str | None,
    outcomes: list[dict],
    event_through: str | None,
    forced_status: str | None = None,
    forced_reason: str | None = None,
) -> dict:
    canonical_id = str(uuid.UUID(run_id))
    started = _timestamp(started_at)
    completed = _timestamp(completed_at)
    if completed < started:
        raise ValueError("completed_at precedes started_at")
    normalized = [validate_outcome(value) for value in outcomes]
    attempted = sorted(outcome["target_date"] for outcome in normalized)
    observed = max(
        (_timestamp(outcome["observed_at"]) for outcome in normalized),
        default=completed,
    )
    if observed < started or observed > completed:
        raise ValueError("outcome observed_at falls outside the run window")
    status = aggregate_status(normalized, forced_status)
    reasons = []
    if forced_reason and forced_reason.strip():
        reasons.append(forced_reason.strip())
    for outcome in normalized:
        if outcome.get("reason") and outcome["reason"] not in reasons:
            reasons.append(outcome["reason"])
    verified_date = _date(verified_through)
    event_date = _date(event_through)
    attempted_through = _date(attempted[-1]) if attempted else None
    if event_date and attempted_through and event_date > attempted_through:
        raise ValueError("event_through exceeds attempted_through")
    return validate_receipt({
        "run_id": canonical_id,
        "collector": "acclaim-mac-launchagent",
        "status": status,
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
        "observed_at": observed.isoformat(),
        "attempted_from": attempted[0] if attempted else None,
        "attempted_through": attempted[-1] if attempted else None,
        "event_through": event_date.isoformat() if event_date else None,
        "verified_through": verified_date.isoformat() if verified_date else None,
        "dates_attempted": len(normalized),
        "rows_observed": sum(outcome["rows_observed"] for outcome in normalized),
        "rows_new": sum(outcome["rows_new"] for outcome in normalized),
        "reason": "; ".join(reasons)[:1000] or None,
        "outcomes": normalized,
    })


def persist_pending(receipt: dict, outbox: Path) -> Path:
    receipt = validate_receipt(receipt)
    outbox.mkdir(parents=True, exist_ok=True)
    destination = outbox / (receipt["run_id"] + ".pending.json")
    if destination.exists():
        existing = json.loads(destination.read_text(encoding="utf-8"))
        if existing != receipt:
            raise ValueError("run_id already has a different pending receipt")
        return destination
    descriptor, temporary_name = tempfile.mkstemp(prefix=".receipt-", dir=outbox)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(receipt, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return destination


def supabase_settings() -> tuple[str, str]:
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get(
        "SUPABASE_SERVICE_KEY", ""
    )
    if not base or not key:
        raise RuntimeError("Supabase receipt destination is not configured")
    return base, key


def post_receipt(receipt: dict, *, urlopen=urllib.request.urlopen) -> None:
    receipt = validate_receipt(receipt)
    base, key = supabase_settings()
    request = urllib.request.Request(
        f"{base}/rest/v1/{TABLE}?on_conflict=run_id",
        method="POST",
        data=json.dumps([receipt], separators=(",", ":")).encode("utf-8"),
        headers={
            "apikey": key,
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Prefer": "resolution=ignore-duplicates,return=minimal",
        },
    )
    with urlopen(request, timeout=60) as response:
        if response.status not in {200, 201, 204}:
            raise RuntimeError("receipt write returned HTTP %s" % response.status)


def mark_sent(pending: Path) -> Path:
    destination = pending.with_name(pending.name.replace(".pending.json", ".sent.json"))
    if destination.exists():
        pending.unlink()
        return destination
    pending.replace(destination)
    return destination


def flush_outbox(outbox: Path, *, post=post_receipt) -> tuple[int, int]:
    sent = failed = 0
    if not outbox.exists():
        return sent, failed
    for pending in sorted(outbox.glob("*.pending.json")):
        try:
            receipt = json.loads(pending.read_text(encoding="utf-8"))
            post(receipt)
            mark_sent(pending)
            sent += 1
        except (OSError, ValueError, RuntimeError):
            failed += 1
    return sent, failed


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    append = commands.add_parser("append")
    append.add_argument("--outcomes-file", required=True, type=Path)
    append.add_argument("--target-date", required=True)
    append.add_argument("--status", required=True, choices=sorted(STATUSES))
    append.add_argument("--pages", required=True, type=int)
    append.add_argument("--rows-observed", required=True, type=int)
    append.add_argument("--rows-new", required=True, type=int)
    append.add_argument("--observed-at", required=True)
    append.add_argument("--reason")

    record = commands.add_parser("record")
    record.add_argument("--run-id", required=True)
    record.add_argument("--started-at", required=True)
    record.add_argument("--completed-at", required=True)
    record.add_argument("--verified-through")
    record.add_argument("--outcomes-file", required=True, type=Path)
    record.add_argument("--state-file", required=True, type=Path)
    record.add_argument("--outbox-dir", required=True, type=Path)
    record.add_argument("--status", choices=sorted(STATUSES))
    record.add_argument("--reason")

    flush = commands.add_parser("flush")
    flush.add_argument("--outbox-dir", required=True, type=Path)
    return root


def main() -> None:
    args = parser().parse_args()
    if args.command == "append":
        append_outcome(
            args.outcomes_file,
            {
                "target_date": args.target_date,
                "status": args.status,
                "pages": args.pages,
                "rows_observed": args.rows_observed,
                "rows_new": args.rows_new,
                "observed_at": args.observed_at,
                "reason": args.reason,
            },
        )
        return
    if args.command == "flush":
        sent, failed = flush_outbox(args.outbox_dir)
        print(json.dumps({"sent": sent, "pending_failed": failed}, sort_keys=True))
        raise SystemExit(1 if failed else 0)

    receipt = build_receipt(
        run_id=args.run_id,
        started_at=args.started_at,
        completed_at=args.completed_at,
        verified_through=args.verified_through,
        outcomes=load_outcomes(args.outcomes_file),
        event_through=event_through_from_state(args.state_file),
        forced_status=args.status,
        forced_reason=args.reason,
    )
    pending = persist_pending(receipt, args.outbox_dir)
    sent = False
    try:
        post_receipt(receipt)
        mark_sent(pending)
        sent = True
    except (OSError, ValueError, RuntimeError) as error:
        print(
            "receipt queued for retry: " + type(error).__name__,
            file=os.sys.stderr,
        )
    print(
        json.dumps(
            {
                "run_id": receipt["run_id"],
                "status": receipt["status"],
                "rows_observed": receipt["rows_observed"],
                "rows_new": receipt["rows_new"],
                "sent": sent,
            },
            sort_keys=True,
        )
    )
    raise SystemExit(0 if sent else 1)


if __name__ == "__main__":
    main()
