# Public API deployment

The public pages remain on GitHub Pages. Browser API calls use
`https://api.thefloridasignal.com`, which terminates TLS in nginx and proxies only `/api/`
to the loopback Python service.

## Runtime

- Checkout: `/srv/grahamandgold/florida-signal-site`
- Unit: `/etc/systemd/system/florida-signal-public.service`
- nginx site: `/etc/nginx/sites-available/api.thefloridasignal.com`
- subscriber/analytics database:
  `/srv/grahamandgold/florida-signal/data/public-api/florida_signal_cms.sqlite`
- optional Mailchimp environment:
  `/srv/grahamandgold/florida-signal/secrets/public-site.env` (mode `0600`)
- DNS: GoDaddy A record `api` -> `142.93.253.188` (600-second TTL when created)
- TLS: Certbot/Let's Encrypt with the system `certbot.timer`

The API service binds only `127.0.0.1:4173`. nginx exposes `/api/`; the remainder of the
subdomain returns 404. CORS is restricted to the root and `www` production origins.

The production checkout is a real Git repository tracking `origin/main`. Do not copy loose files
over it. Before updating the API, require a clean checkout, fetch `main`, inspect the incoming diff,
run the API tests, fast-forward only, restart the service and verify the public HTTPS boundary.

## Initial installation

```sh
sudo install -m 0644 ops/droplet/florida-signal-public.service /etc/systemd/system/
sudo install -m 0644 ops/droplet/nginx-api.thefloridasignal.com.conf \
  /etc/nginx/sites-available/api.thefloridasignal.com
sudo ln -s /etc/nginx/sites-available/api.thefloridasignal.com \
  /etc/nginx/sites-enabled/api.thefloridasignal.com
sudo ufw allow 'Nginx Full'
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now florida-signal-public.service
sudo systemctl reload nginx
```

After authoritative DNS resolves to the host, install and configure TLS:

```sh
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.thefloridasignal.com --redirect
sudo certbot renew --dry-run
systemctl is-enabled certbot.timer
systemctl is-active certbot.timer
```

Certbot owns the generated TLS directives in the live nginx file. The tracked nginx file is the
HTTP bootstrap configuration used before certificate issuance.

## Secrets and durable data

`public-site.env` must contain plain systemd assignments (`NAME=value`), not shell statements such
as `export NAME=value`. Keep it `root:root` and mode `0600`. Never print or commit its values.

The service writes only inside the public API data directory. Keep the directory `0700` and the
SQLite database `0600`, both owned by the service user. Back up the database before runtime or
schema changes. Deployment must never delete subscriber or analytics rows.

## Updating production

```sh
cd /srv/grahamandgold/florida-signal-site
git status --short
git fetch origin main
git diff --stat HEAD..origin/main -- server.py tests ops/droplet
python3 -m unittest discover -s tests -v
git merge --ff-only origin/main
sudo systemctl restart florida-signal-public.service
curl -fsS http://127.0.0.1:4173/api/health
curl -fsS https://api.thefloridasignal.com/api/health
```

Stop if the checkout is dirty, the update is not a fast-forward, tests fail, or the incoming change
modifies source/data semantics without a reconciliation record.

## Verification

```sh
curl -fsS http://127.0.0.1:4173/api/health
curl -fsS https://api.thefloridasignal.com/api/health
curl -fsS https://api.thefloridasignal.com/api/data-health
systemctl show florida-signal-public.service -p ActiveState,SubState,Result,ExecMainStatus
systemctl show certbot.timer -p ActiveState,UnitFileState,NextElapseUSecRealtime
sudo nginx -t
```

Expected integration state on August 11, 2026:

- `mailchimp_configured: true` after a read-only audience authentication check;
- `cms_configured: false` because the private Data Wire is not exposed on this host;
- `/api/cms` returns no drafts and enforces the approved-only gate;
- `/api/data-health` may legitimately report stale/unverified source clocks and must not be coerced green;
- `/api/storms` may return 502 when NHC blocks the host; the client must show a source-check state and
  link to the official NHC source rather than claim there are no storms.

## Rollback

Disable the unit and nginx site, then restore `app.js` to same-origin API URLs. Existing
subscriber rows remain in the SQLite database and are not deleted by rollback. The pre-deploy
database and prior unversioned runtime are preserved at the paths recorded in
`SYSTEM_STATE_2026-08-11.md`; copy them to a new recovery path before inspecting or restoring them.
