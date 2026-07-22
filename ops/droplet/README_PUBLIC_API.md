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

The API service binds only `127.0.0.1:4173`. nginx exposes `/api/`; the remainder of the
subdomain returns 404. CORS is restricted to the root and `www` production origins.

## Verification

```sh
curl -fsS http://127.0.0.1:4173/api/health
curl -fsS https://api.thefloridasignal.com/api/health
systemctl show florida-signal-public.service -p ActiveState,SubState,Result,ExecMainStatus
```

## Rollback

Disable the unit and nginx site, then restore `app.js` to same-origin API URLs. Existing
subscriber rows remain in the SQLite database and are not deleted by rollback.
