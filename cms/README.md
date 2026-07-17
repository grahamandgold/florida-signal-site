# The Data Wire — Florida Desk CMS

The Data Wire is the source-gated editorial CMS that powers Florida Signal and is designed to support additional market sites without mixing their public feeds.

It is a focused, clean-room port of the useful Michigan Intel Desk patterns:

- private draft queues never appear on a public endpoint;
- every story/brief carries both a `market` key and a required `city` key;
- source, claims, taxonomy and human-editor checks must all pass;
- the public site reads only `/api/wire/packets?market=broward&city=fort-lauderdale` and `/api/agenda-recon?market=broward`;
- Agenda Recon properties require a cited official source, coordinates and explicit clearance;
- newsletter/social candidates are downstream views of an approved packet, never separate unsourced copy.

The Michigan repository is not imported or modified. The Data Wire starts empty; it deliberately contains no sample story that could be mistaken for real reporting.

## Run locally

```bash
export DATA_WIRE_ADMIN_TOKEN='use-a-long-local-secret'
python3 cms/server.py --port 8788
```

Then run the public site with:

```bash
export FLORIDA_SIGNAL_CMS_URL='http://127.0.0.1:8788'
export FLORIDA_SIGNAL_CMS_MARKET='broward'
export FLORIDA_SIGNAL_CMS_CITY='fort-lauderdale'
python3 server.py --port 4173
```

Open `http://127.0.0.1:8788/` for the local editorial desk. The browser stores the admin token only in the local session. Do not put it in public JavaScript, a screenshot or a committed file.

### If the desk says Locked

The lock is deliberate. Use the exact value you supplied as `DATA_WIRE_ADMIN_TOKEN` when starting the server:

1. Choose market `broward`.
2. Paste the token into **Private desk token**.
3. Choose **Open desk**.

If the token is rejected, stop the CMS process, export a new long private token, restart `cms/server.py`, then paste that new value. The public site does not need or receive the admin token.

## Public endpoints

- `GET /api/health`
- `GET /api/wire/packets?market=broward&city=fort-lauderdale`
- `GET /api/agenda-recon?market=broward`

## Private endpoints

Send `Authorization: Bearer $DATA_WIRE_ADMIN_TOKEN`.

- `GET /api/admin/stories?market=broward`
- `POST /api/admin/stories`
- `POST /api/admin/stories/{id}/approve`
- `POST /api/admin/stories/{id}/hold`
- `POST /api/admin/agenda-recon`
- `POST /api/admin/agenda-recon/{id}/clear`

## Approval contract

A brief cannot publish until it is a complete **VERIFIED Story Packet**: required city, headline, dek, body, event date, dated current trigger, defensible project identity, public source URL/title, at least one source-bound claim slot, topic and geography tags, `claims_status: passed`, `validator_status: passed`, `tags_status: passed`, and a named human editor. Needs-verification packets remain private. The CMS computes a source hash and records approval history.

An agenda-property item cannot publish until it has an official packet URL, meeting title/date, item number, property address, coordinates, proposed action, source page and a named human editor.

## Production work still required

- deploy behind authentication and HTTPS;
- move SQLite to private persistent Postgres/Supabase;
- configure backups and audit-log retention;
- connect the official agenda/record collectors to the private draft API;
- add a user/role provider instead of a shared admin token;
- keep all AI output in draft status until a human passes the source and claims gates.
