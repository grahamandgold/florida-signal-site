#!/usr/bin/env python3
"""Broward Clerk SFTP catch-up (droplet edition).

Ingests any published business dates missing from broward_clerk_records_run.
Idempotent: natural-key ON CONFLICT via PostgREST ignore-duplicates.
Reads SUPABASE_URL + a WRITE key (SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SERVICE_KEY) from env.
Reads BROWARD_SFTP_USER + BROWARD_SFTP_PASS from env; exits if either is absent.
Never deletes. Never updates existing rows. Event date = file business date.

WRITE ORDER (repaired 2026-07-20, see docs/DECISION_LOG):
  A. one run_id generated per business date
  B. read + hash + parse all four source files into memory (no writes)
  C. build the parent run record from completed hashes/counts
  D. INSERT the parent broward_clerk_records_run row FIRST
  E. only then INSERT the four child tables
  F. parent-insert failure => zero child writes, nonzero exit
  G. reconcile Acclaim preliminary rows after every run, including no-op runs

Every child table carries FOREIGN KEY (run_id) REFERENCES
broward_clerk_records_run(run_id) with cascading delete. Writing children first
therefore always violates the FK. Prior to this repair the parent was written
last and run_id was regenerated per file, so the ingest path could never
succeed; it was masked because the script short-circuits when nothing is due.
"""
import io, json, os, re, sys, hashlib, datetime, urllib.request, urllib.error
import paramiko

HOST, RDIR = "bcftp.broward.org", "/Official_Records_Download"
USER = os.environ.get("BROWARD_SFTP_USER", "").strip()
PW = os.environ.get("BROWARD_SFTP_PASS", "").strip()
if not USER or not PW:
    sys.exit(
        "FATAL: BROWARD_SFTP_USER and BROWARD_SFTP_PASS must both be set. "
        "They are supplied by the systemd EnvironmentFile "
        "(/srv/grahamandgold/florida-signal/secrets/.env). Refusing to connect."
    )
SB = os.environ.get("SUPABASE_URL", "https://jrjewmzkyluxdywyusrw.supabase.co").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY") or ""
ANON = os.environ.get("SUPABASE_ANON_KEY", "sb_publishable_dEyBjKE_vcTj3YYx4p6XvA_xnkVW3Wb")
MAX_DATES = int(os.environ.get("CLERK_CATCHUP_MAX_DATES", "10"))
RUN_PAGE_SIZE = 1000
VERBOSE_ERRORS = os.environ.get("CLERK_CATCHUP_VERBOSE_ERRORS", "") == "1"

DOC_COLS = ["instrument_number","recording_date_raw","recording_date_disp","recording_time_hms","doc_type_code","consideration_amount","doc_field_06","doc_field_07","side_flag","confidential_flag","rerecord_flag","documentary_tax","intangible_tax","number_of_names","number_of_legals","verified_flag","doc_field_16","doc_field_17","doc_field_18","doc_field_19"]
NME_COLS = ["instrument_number","name","role_code","sequence_number","party_field_04"]
LGL_COLS = ["instrument_number","legal_description","parcel_id","legal_field_03"]
LNK_COLS = ["source_instrument_number","link_field_01","link_field_02","source_side_flag","source_doc_type","target_instrument_number","link_field_06","link_field_07","target_side_flag","target_doc_type","display_label","link_field_11"]
NUMERIC = {"consideration_amount","documentary_tax","intangible_tax","number_of_names","number_of_legals","sequence_number"}

PARENT_TABLE = "broward_clerk_records_run"
# (file suffix, child table, columns, natural-key conflict target)
CHILD_SPECS = [
    ("doc-ver", "broward_clerk_records_doc",   DOC_COLS, "business_date,instrument_number"),
    ("nme-ver", "broward_clerk_records_party", NME_COLS, "business_date,instrument_number,role_code,sequence_number"),
    ("lgl-ver", "broward_clerk_records_legal", LGL_COLS, "business_date,source_row_number"),
    ("lnk-ver", "broward_clerk_records_link",  LNK_COLS, "business_date,source_row_number"),
]


class RestError(Exception):
    """HTTP failure with sanitised diagnostics.

    Deliberately carries no credentials, headers, full URL or request payload.
    PostgREST error `code` and `message` are schema-level and safe to log;
    `details`/`hint` can echo row values (party names) and are withheld unless
    CLERK_CATCHUP_VERBOSE_ERRORS=1 is set for interactive debugging.
    """

    def __init__(self, status, path, operation, body=None, business_date=None):
        self.status = status
        self.path = path
        self.operation = operation
        self.business_date = business_date
        self.code, self.message, self.extra = _sanitise_error_body(body)
        super().__init__(str(self))

    def __str__(self):
        bits = [f"HTTP {self.status}", f"op={self.operation}", f"path={self.path}"]
        if self.business_date:
            bits.append(f"business_date={self.business_date}")
        if self.code:
            bits.append(f"pg_code={self.code}")
        if self.message:
            bits.append(f"pg_message={self.message}")
        if self.extra:
            bits.append(f"pg_details={self.extra}")
        return " | ".join(bits)


def _sanitise_error_body(body):
    """Return (code, message, extra) with row-level values withheld by default."""
    if not body:
        return None, None, None
    try:
        parsed = json.loads(body)
    except Exception:
        text = str(body)[:200]
        return None, text, None
    if not isinstance(parsed, dict):
        return None, str(parsed)[:200], None
    code = parsed.get("code")
    message = parsed.get("message")
    extra = None
    if VERBOSE_ERRORS:
        extra = "; ".join(
            str(parsed.get(k))[:200] for k in ("details", "hint") if parsed.get(k)
        ) or None
    return code, message, extra


def rest(path, method="GET", payload=None, key=None, prefer=None, business_date=None, operation=None):
    req = urllib.request.Request(SB + "/rest/v1/" + path, method=method)
    k = key or ANON
    req.add_header("apikey", k); req.add_header("Authorization", "Bearer " + k)
    req.add_header("Content-Type", "application/json")
    if prefer: req.add_header("Prefer", prefer)
    data = json.dumps(payload).encode() if payload is not None else None
    op = operation or method
    try:
        with urllib.request.urlopen(req, data=data, timeout=60) as r:
            body = r.read().decode() or "[]"
            return json.loads(body) if body.strip().startswith(("[", "{")) else body
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", "replace")
        except Exception:
            err_body = None
        raise RestError(e.code, path.split("?")[0], op, err_body, business_date) from None


def parse_rows(text, cols, bd, run_id, ftype):
    out = []
    for i, line in enumerate(io.StringIO(text), start=1):
        line = line.rstrip("\r\n")
        if not line: continue
        parts = line.split("|")
        row = {"business_date": bd, "run_id": run_id, "source_file_type": ftype, "source_row_number": i}
        for j, col in enumerate(cols):
            val = parts[j].strip() if j < len(parts) else ""
            if col == "recording_date_raw":
                row["recording_date_iso"] = f"{val[0:4]}-{val[4:6]}-{val[6:8]}" if re.fullmatch(r"\d{8}", val) else None
                continue
            if col in NUMERIC: row[col] = float(val) if re.fullmatch(r"-?\d+(\.\d+)?", val) else (None if col not in ("number_of_names","number_of_legals","sequence_number") else 0)
            else: row[col] = val
        for c in ("number_of_names","number_of_legals","sequence_number"):
            if c in row and row[c] is not None: row[c] = int(row[c])
        out.append(row)
    return out


def insert(table, rows, conflict, business_date=None):
    for i in range(0, len(rows), 400):
        rest(f"{table}?on_conflict={conflict}", "POST", rows[i:i+400], key=KEY,
             prefer="resolution=ignore-duplicates,return=minimal",
             business_date=business_date, operation=f"insert_child:{table}")


def make_run_id(iso, now=None):
    """One run_id per business date. Generated ONCE, outside the file loop."""
    stamp = (now or datetime.datetime.utcnow()).strftime("%Y%m%d_%H%M%S")
    return f"broward_clerk_records_{stamp}_bd_{iso.replace('-','')}"


def read_and_parse(sftp, d, iso, run_id):
    """PHASE B: read, hash and parse every source file. Performs NO writes."""
    parsed, shas, counts = [], {}, {}
    for suffix, tbl, cols, conflict in CHILD_SPECS:
        raw = sftp.open(f"{RDIR}/{d}{suffix}.txt").read()
        shas[suffix] = hashlib.sha256(raw).hexdigest()
        rows = parse_rows(raw.decode("utf-8", "replace"), cols, iso, run_id, suffix)
        counts[suffix] = len(rows)
        parsed.append((tbl, rows, conflict))
    return parsed, shas, counts


def build_parent_record(run_id, iso, shas, counts):
    """PHASE C: parent row built from COMPLETED hashes and counts."""
    stamp = datetime.datetime.utcnow().isoformat()
    return {
        "run_id": run_id, "business_date": iso, "source_host": HOST, "source_dir": RDIR,
        "parse_status": "ok", "pulled_at_utc": stamp, "parsed_at_utc": stamp,
        "doc_sha256": shas["doc-ver"], "nme_sha256": shas["nme-ver"],
        "lgl_sha256": shas["lgl-ver"], "lnk_sha256": shas["lnk-ver"],
        "expected_doc_count": counts["doc-ver"], "observed_doc_count": counts["doc-ver"],
        "observed_party_count": counts["nme-ver"], "observed_legal_count": counts["lgl-ver"],
        "observed_link_count": counts["lnk-ver"],
    }


def insert_parent(record, business_date=None):
    """PHASE D: parent FIRST. broward_clerk_records_run PK is (run_id)."""
    rest(PARENT_TABLE, "POST", [record], key=KEY,
         prefer="resolution=ignore-duplicates,return=minimal",
         business_date=business_date, operation="insert_parent")


def ingest_date(sftp, d, iso):
    """Ingest exactly one business date. Returns the run_id on success."""
    run_id = make_run_id(iso)                                   # A
    parsed, shas, counts = read_and_parse(sftp, d, iso, run_id) # B
    record = build_parent_record(run_id, iso, shas, counts)     # C
    try:
        insert_parent(record, business_date=iso)                # D
    except RestError as e:                                      # F
        print(f"FATAL: parent insert failed for business_date={iso}; "
              f"zero child rows were attempted. {e}", file=sys.stderr)
        raise
    for tbl, rows, conflict in parsed:                          # E
        try:
            insert(tbl, rows, conflict, business_date=iso)
        except RestError as e:
            print(
                f"FATAL: child insert failed for business_date={iso} table={tbl} "
                f"AFTER the parent row was written. run_id={run_id}. "
                f"This date will now appear ingested and will be SKIPPED on retry. "
                f"Remove the parent row for this run_id (the cascade constraint clears "
                f"any partial children) before re-running. {e}",
                file=sys.stderr,
            )
            raise
    print(f"ingested bd {iso}: run_id={run_id} docs={counts['doc-ver']} "
          f"parties={counts['nme-ver']} legals={counts['lgl-ver']} links={counts['lnk-ver']}")
    return run_id


def reconcile_preliminary():
    """Reconcile Acclaim rows immediately after the authoritative feed advances.

    The server-side function preserves preliminary source fields, marks exact
    instrument/date matches verified, and quarantines date conflicts. The
    independent daily pg_cron job remains a fallback; calling the function here
    removes the normal several-hour reconciliation delay.
    """
    result = rest(
        "rpc/reconcile_clerk_preliminary",
        "POST",
        {},
        key=KEY,
        prefer="return=representation",
        operation="reconcile_preliminary",
    )
    if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], dict):
        raise RuntimeError("reconcile_clerk_preliminary returned an unexpected response shape")
    audit = result[0]
    print(
        "preliminary reconciliation: "
        f"matched={audit.get('matched', 0)} "
        f"conflicts={audit.get('conflicts', 0)} "
        f"aged_unmatched={audit.get('aged_unmatched', 0)}"
    )
    return audit


def existing_business_dates(page_size=RUN_PAGE_SIZE):
    """Read the complete run ledger; PostgREST otherwise stops at its first 1,000 rows."""
    dates, offset = set(), 0
    while True:
        rows = rest(
            f"{PARENT_TABLE}?select=business_date&order=business_date.asc"
            f"&limit={page_size}&offset={offset}",
            operation="select_have",
        )
        dates.update(row["business_date"] for row in rows if row.get("business_date"))
        if len(rows) < page_size:
            return dates
        offset += page_size


def main():
    if not KEY: sys.exit("FATAL: no service key in env (SUPABASE_SERVICE_ROLE_KEY)")
    have = existing_business_dates()
    t = paramiko.Transport((HOST, 22)); t.connect(username=USER, password=PW)
    sftp = paramiko.SFTPClient.from_transport(t)
    ingest_failed = False
    try:
        names = sftp.listdir(RDIR)
        dates = sorted({m.group(1) for n in names if (m := re.match(r"(\d{2}-\d{2}-\d{4})doc-ver\.txt$", n))})
        todo = []
        for d in dates:
            mm, dd, yy = d.split("-"); iso = f"{yy}-{mm}-{dd}"
            if iso not in have: todo.append((d, iso))
        todo = todo[:MAX_DATES]
        if not todo:
            print("Nothing to ingest; verified table matches server.")
        for d, iso in todo:
            try:
                ingest_date(sftp, d, iso)
            except RestError:
                # Deterministic: stop immediately, do not attempt later dates.
                ingest_failed = True
                break
    finally:
        t.close()
    try:
        reconcile_preliminary()
    except (RestError, RuntimeError) as e:
        print(f"FATAL: preliminary reconciliation failed. {e}", file=sys.stderr)
        return 2 if ingest_failed else 3
    return 2 if ingest_failed else 0


if __name__ == "__main__":
    sys.exit(main())
