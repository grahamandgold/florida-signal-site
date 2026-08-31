# Fort Lauderdale utility/engineering-intake shadow view

**State:** code and fixture tests only. This runbook does not authorize deployment, a
timer, production SQLite mutation, a Supabase write, Candidate scoring, a Desk
`connected` label, promotion or publication.

**Collector:** `ops/droplet/utility_intake_shadow.py`

## What this view proves

The collector reads an **explicitly supplied** SQLite database in query-only mode
and writes one immutable local observation bundle for exact Fort Lauderdale
record-number families already stored there. It is a shadow view of existing
LauderBuild/Accela rows, not a new Accela search path and not a production
detector.

It classifies only these reviewed families:

| Family | Meaning |
|---|---|
| `ENG-CR-*` | water/wastewater capacity availability requests; **parent record numbers only** |
| `ENG-OAA-*` | outside-agency engineering intake; **parent record numbers only** |
| `ROW-SEW-*` | sewer right-of-way work, including reviewed dotted subpermit identities |
| `ROW-WTR-*` | water right-of-way work, including reviewed dotted subpermit identities |
| `PLB-SEWCP-WT-*` | sewer-cap walk-through records, including reviewed dotted subpermit identities |

Matching is exact hyphen-delimited family tokens, not a string startswith.
`ENG-CR-*` and `ENG-OAA-*` admit parent record numbers only; dotted identities
such as `ENG-CR-26010001.D001` are unknown, not matches. Broad `ENG-*`, `ROW-*`,
`PLB-*` and `TMP-*` records are counted as unknown, never admitted. Generic
`ROW-SEWER-*` or `PLB-SEWCP-*` (without `WT`) do not match.

This view does not claim that any family is earlier than Preliminary Development
Meeting Request (PDMR) records or other permits. A Fort Lauderdale result does
not establish Broward Water and Wastewater Services coverage.

## Read-only snapshot contract

CLI/live runs require three explicit absolute paths:

- `--sqlite-path` — existing SQLite file
- `--writer-lock-path` — existing writer-lock file; must already exist
- `--output-dir` — create-only bundle root

The collector acquires a **nonblocking shared `flock`** on the writer-lock file
before scanning and holds it through the read. If an exclusive writer owns the
lock, the run fails closed and does not create a bundle. The lock file is never
created by this collector. The receipt records the held lock file's path and
requires its `stat` identity to remain unchanged; replacement or removal while
the lock is held fails the run.

While the shared lock is held, and before the read, it captures the database and
sidecar file identities. A rollback `-journal` or an incomplete `-wal`/`-shm`
pair fails closed. A real WAL pair is supported only when SQLite itself reports
`journal_mode=wal`: the main database and WAL stats, WAL/SHM presence, and SHM
file identity must remain stable through the read. SHM size/mtime may change as
SQLite registers a reader and is recorded rather than misclassified as a source
row, main-database or WAL-content write. Any sidecar presence change fails
closed because the collector cannot attribute which process created it. The
receipt explicitly does not claim
zero filesystem mutation because normal SQLite readers can update transient SHM
reader metadata. After the read, still under the lock, it recaptures all evidence. It opens
the database as `file:...?mode=ro` with
`PRAGMA query_only=ON`, begins one `BEGIN DEFERRED` read transaction, records
`PRAGMA data_version` before the transaction and again after `COMMIT`, requires
them to match, and records
`PRAGMA quick_check` for `permits` (and `accela_details` when present).
The receipt says only that this query-only collector issued zero source-row,
main-database-content and WAL-content writes. Observed database/WAL stability is
reported separately under `quality` and may fail if another process ignored the
cooperative lock. Transient SHM reader metadata may change. The shared lock is
released before JSON output is written.

There is no network client and no wet-mode flag. The result always says
`mode=shadow_file_only`, `promotion_eligible=false` and
`connected_label_allowed=false`.

## Live file-only canary — 2026-08-31

The reviewed V5 collector ran against canonical production SQLite under the
actual live application lock at 19:22:51–19:23:17 EDT. Its immutable receipt is:

`/srv/grahamandgold/florida-signal/app/data/audit/utility-intake-shadow/utility-intake-shadow-20260831T1926EDT/receipt.json`

It returned `status=ok`, scanned 137,942 stored permit identities, admitted 523,
rejected 0 and classified 137,419 as unknown/non-target. Exact admitted-family
counts were ENG-CR 166, ENG-OAA 75, PLB-SEWCP-WT 193, ROW-SEW 89 and ROW-WTR 0.
The zero is only an observation of this complete stored-SQLite snapshot; it is
not proof that the source system or serving utility has no ROW-WTR work.

The receipt records query-only SQL, stable `data_version`, stable main-database
stat, stable zero-byte WAL, stable SHM identity, both table quick checks `ok`,
exact accounting and no collector-issued database/WAL content writes. Its
logical input fingerprint is
`69cff86fe1bfc0ddbc2bdb72bff6d6012371c336eaffb3367b18eb0186fb8477`.
This validates the file-only evidence contract only. It does not authorize a
timer, network collector, Supabase mirror, scoring, Desk-connected label,
promotion or publication.

An earlier V4 attempt at 19:12:58 failed closed when WAL/SHM presence changed
during the read. Its receipt and partial evidence bundle remain preserved under
`utility-intake-shadow-20260831T1913EDT`; the main database stat and row content
did not change. V5 keeps that conservative fail-closed rule and scopes all write
claims to writes issued by this collector.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 ops/droplet/utility_intake_shadow.py \
  --sqlite-path /absolute/path/to/permits.sqlite \
  --writer-lock-path /absolute/path/to/db/.writer.lock \
  --output-dir /private/tmp/florida-signal-utility-intake-shadow \
  --run-id utility-intake-shadow-review
```

The run directory is never overwritten. Reusing a `run_id` fails.

## Contract-relevant logical fingerprint

The receipt binds a **contract-relevant logical projection fingerprint**, not a
byte-for-byte database file SHA-256 and not a hash of the exact or complete
database snapshot. The collector does not hash the entire SQLite file and does
not hash unknown-row source content.

`hashes.logical_input_database_fingerprint` is SHA-256 of that bounded
projection:

- schema projection
- SQLite metadata (`data_version`, page count/size, user/application/schema
  version, encoding, journal mode)
- total rows scanned
- admitted / unknown / rejected accounting
- admitted content index, rejected index, and unknown identity list

File `stat` is recorded separately as snapshot-stability evidence. Do not
describe the logical fingerprint as a file SHA or as an exact snapshot hash.

## Clocks and secrets

Application, event, source-modified and pull clocks remain distinct. Missing
clocks are `UNKNOWN_*`. The collector generated-at clock is never a source
event. Generic `last_updated_at` is retained as a raw field when present and is
**not** a source-modified clock. An explicit nonempty `source_modified_at` or
`source_last_modified_at` on a supporting `accela_details` row is preferred;
otherwise the same qualified column on `permits` is used. Cap-ID prefers a
parseable supporting `source_url` and falls back to a valid permits `source_url`.

Secret-like keys are redacted at any nesting depth, including JSON objects
stored in `raw_json`. Unparseable structured text that still matches a
secret-like key pattern is omitted.

## Evidence bundle

Each create-only run directory contains:

| File | Purpose |
|---|---|
| `observation-bundle.json` | Immutable JSON observation bundle with admitted and rejected rows |
| `shadow-records.jsonl` | Deterministically ordered admitted family rows |
| `shadow-content-index.jsonl` | Identity-sorted content hashes excluding collector clocks |
| `rejected-records.jsonl` | Malformed or duplicate identities |
| `receipt.json` | Terminal status, counts, clocks, versions, hashes and safety assertions |
| `bundle-manifest.json` | Top-level hashes binding the bundle together |

Accounting is exact:

```text
rows_scanned = rows_admitted + rows_rejected + rows_unknown
```

If a required evidence field is absent from the supplied schema, the view fails
closed or labels that field `UNKNOWN`. It does not invent Cap-ID tuples, DRC
case numbers, serving-utility coverage or source-modified times.

## Safety

- No production SQLite mutation.
- No Supabase, timer, service, queue, Candidate, scoring, Desk green status or
  publication path.
- Secret-like keys, including nested JSON, are redacted or omitted.
