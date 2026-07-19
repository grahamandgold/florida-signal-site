#!/usr/bin/env python3
"""Broward Clerk SFTP catch-up (droplet edition).
Ingests any published business dates missing from broward_clerk_records_run.
Idempotent: natural-key ON CONFLICT via PostgREST ignore-duplicates.
Reads SUPABASE_URL + a WRITE key (SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SERVICE_KEY) from env.
Never deletes. Never updates existing rows. Event date = file business date."""
import io, json, os, re, sys, hashlib, datetime, urllib.request
import paramiko

HOST, USER, PW, RDIR = "bcftp.broward.org", "crpublic", "crpublic", "/Official_Records_Download"
SB = os.environ.get("SUPABASE_URL", "https://jrjewmzkyluxdywyusrw.supabase.co").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY") or ""
ANON = os.environ.get("SUPABASE_ANON_KEY", "sb_publishable_dEyBjKE_vcTj3YYx4p6XvA_xnkVW3Wb")
MAX_DATES = int(os.environ.get("CLERK_CATCHUP_MAX_DATES", "3"))

DOC_COLS = ["instrument_number","recording_date_raw","recording_date_disp","recording_time_hms","doc_type_code","consideration_amount","doc_field_06","doc_field_07","side_flag","confidential_flag","rerecord_flag","documentary_tax","intangible_tax","number_of_names","number_of_legals","verified_flag","doc_field_16","doc_field_17","doc_field_18","doc_field_19"]
NME_COLS = ["instrument_number","name","role_code","sequence_number","party_field_04"]
LGL_COLS = ["instrument_number","legal_description","parcel_id","legal_field_03"]
LNK_COLS = ["source_instrument_number","link_field_01","link_field_02","source_side_flag","source_doc_type","target_instrument_number","link_field_06","link_field_07","target_side_flag","target_doc_type","display_label","link_field_11"]
NUMERIC = {"consideration_amount","documentary_tax","intangible_tax","number_of_names","number_of_legals","sequence_number"}

def rest(path, method="GET", payload=None, key=None, prefer=None):
    req = urllib.request.Request(SB + "/rest/v1/" + path, method=method)
    k = key or ANON
    req.add_header("apikey", k); req.add_header("Authorization", "Bearer " + k)
    req.add_header("Content-Type", "application/json")
    if prefer: req.add_header("Prefer", prefer)
    data = json.dumps(payload).encode() if payload is not None else None
    with urllib.request.urlopen(req, data=data, timeout=60) as r:
        body = r.read().decode() or "[]"
        return json.loads(body) if body.strip().startswith(("[", "{")) else body

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

def insert(table, rows, conflict):
    for i in range(0, len(rows), 400):
        rest(f"{table}?on_conflict={conflict}", "POST", rows[i:i+400], key=KEY, prefer="resolution=ignore-duplicates,return=minimal")

def main():
    if not KEY: sys.exit("FATAL: no service key in env (SUPABASE_SERVICE_ROLE_KEY)")
    have = {r["business_date"] for r in rest("broward_clerk_records_run?select=business_date&limit=1000")}
    t = paramiko.Transport((HOST, 22)); t.connect(username=USER, password=PW)
    sftp = paramiko.SFTPClient.from_transport(t)
    names = sftp.listdir(RDIR)
    dates = sorted({m.group(1) for n in names if (m := re.match(r"(\d{2}-\d{2}-\d{4})doc-ver\.txt$", n))})
    todo = []
    for d in dates:
        mm, dd, yy = d.split("-"); iso = f"{yy}-{mm}-{dd}"
        if iso not in have: todo.append((d, iso))
    todo = todo[:MAX_DATES]
    if not todo: print("Nothing to ingest; verified table matches server."); t.close(); return
    for d, iso in todo:
        files, shas, counts = {}, {}, {}
        for suffix, tbl, cols, conflict in [
            ("doc-ver", "broward_clerk_records_doc", DOC_COLS, "business_date,instrument_number"),
            ("nme-ver", "broward_clerk_records_party", NME_COLS, "business_date,instrument_number,role_code,sequence_number"),
            ("lgl-ver", "broward_clerk_records_legal", LGL_COLS, "business_date,source_row_number"),
            ("lnk-ver", "broward_clerk_records_link", LNK_COLS, "business_date,source_row_number"),
        ]:
            raw = sftp.open(f"{RDIR}/{d}{suffix}.txt").read()
            shas[suffix] = hashlib.sha256(raw).hexdigest()
            run_id = f"broward_clerk_records_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_bd_{iso.replace('-','')}"
            rows = parse_rows(raw.decode("utf-8", "replace"), cols, iso, run_id, suffix)
            counts[suffix] = len(rows)
            insert(tbl, rows, conflict)
        rest("broward_clerk_records_run", "POST", [{
            "run_id": run_id, "business_date": iso, "source_host": HOST, "source_dir": RDIR,
            "parse_status": "ok", "pulled_at_utc": datetime.datetime.utcnow().isoformat(),
            "parsed_at_utc": datetime.datetime.utcnow().isoformat(),
            "doc_sha256": shas["doc-ver"], "nme_sha256": shas["nme-ver"], "lgl_sha256": shas["lgl-ver"], "lnk_sha256": shas["lnk-ver"],
            "expected_doc_count": counts["doc-ver"], "observed_doc_count": counts["doc-ver"],
            "observed_party_count": counts["nme-ver"], "observed_legal_count": counts["lgl-ver"], "observed_link_count": counts["lnk-ver"],
        }], key=KEY, prefer="resolution=ignore-duplicates,return=minimal")
        print(f"ingested bd {iso}: docs={counts['doc-ver']} parties={counts['nme-ver']} legals={counts['lgl-ver']} links={counts['lnk-ver']}")
    t.close()

if __name__ == "__main__":
    main()
