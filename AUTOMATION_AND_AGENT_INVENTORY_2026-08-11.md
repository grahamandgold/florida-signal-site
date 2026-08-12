# Florida Signal — automation and agent inventory

**Recorded August 11–12, 2026 · inventory before integration**

This file separates things that actually run from things that merely exist in an account, browser,
repo or conversation. Do not call every scheduled job an “agent,” and do not connect a model to
production data or publishing merely because a connector is available.

## What runs now

| System | Type | Owner / location | Authority | Current state |
|---|---|---|---|---|
| Florida production timers | deterministic collectors/refreshes | DigitalOcean systemd, scorer repo | Read/write their assigned source tables and caches | Active; visible read-only in the Data Wire pipeline strip |
| Supabase scheduled jobs | database functions / source sync | production Supabase project | Narrow database functions | Active where documented; each source needs its own event/system clock |
| `com.floridasignal.acclaim` | native Mac LaunchAgent | `ops/mac/` + logged-in Chrome | Sole writer to preliminary Acclaim lane | Active, hourly/login/fixed checkpoints, last exit 0 |
| GitHub site monitor | deterministic browser/health check | GitHub Actions | Read-only public checks and alerts | Active; must not publish editorial content |
| Human editorial desk | decision gate | local Data Wire | Approve/hold/reject Candidate; Story gate separate | Active locally; approval does not publish |

## Model work completed tonight

| Tool | Work performed | Continuous maintainer? | Production authority? |
|---|---|---:|---:|
| Codex primary chat | Pipeline audit, permanent fixes, Data Wire implementation, tests and docs | No; active only while the chat works | Local code changes and explicitly requested operations only |
| Three Codex sub-agents | One-time mobile, desktop and journalism/product audits | No; finished | Read-only audit |
| Claude Cowork | One-time Data Wire UX/intelligence audit | No | Read-only audit/document work |
| Claude Design | Six-view interface concept and requested editorial corrections | No | Prototype only; no production deployment |
| Grok open-web research | Investigation Kit prompt/link only | No | Leads only; never evidence or approval |

## Claude schedules audited

- `broward-sameday-recordings` — paused, preserved as emergency rollback; the native LaunchAgent is
  the only normal writer.
- `florida-shadow-run-review` — paused; it was a completed July gate still running daily.
- `regenerate-social-graphics` — paused; the 21:40 run was stopped. Its ten incidental PNG changes
  must stay outside the intended commit until separately reviewed.

These paused schedules are not the Florida production pipeline. Production systemd/Supabase jobs
and the native Acclaim LaunchAgent remain independent.

## Known to exist but not yet audited

- Grok “agents” visible in the signed-in Grok account: **unverified**. We have not recorded their
  prompts, schedules, tools, permissions, write targets, stop conditions or history.
- Claude API connectors/integrations: **partially observed but not inventoried**. Availability does
  not mean Florida Signal uses them. Supabase, Chrome and local-computer access appeared in historical
  task runs; their precise grants must be reviewed before any new loop.
- Claude Projects/Cowork history contains old Florida and Michigan work. A conversation title or
  project membership is not proof that anything currently runs.
- Mailchimp is configured for the production API/account workflow, but no AI campaign agent is an
  approved publisher.
- The Michigan Wire repository may contain reusable logic; it is not a Florida production service
  and must be evaluated as code, not assumed compatible.

## What the two X posts contribute

- [Claude capability guide](https://x.com/anatolikopadze/status/2087164089420206263?s=46): useful
  inventory ideas—Projects, memory, roles, browser/Cowork, scheduled tasks, skills, `CLAUDE.md`,
  Design and prompt caching. Florida Signal should use only the pieces with explicit ownership,
  permissions and evidence contracts.
- [Loop vs graph vs harness engineering](https://x.com/arle0x/status/2086467552373317842?s=46): the
  stronger architecture frame. A harness supplies tools/state/permissions/traces; a loop supplies
  measurable feedback/retry/stop rules; a graph supplies explicit stages, branches, joins and human
  gates. Florida Signal currently has parts of the harness and deterministic collection loops, not a
  complete autonomous editorial graph.

## Safe target architecture

```text
source ingest
  → deterministic normalize / dedupe / clock checks
  → source-specific Candidate detectors
  → sealed, minimized evidence packet
  → specialist research leads (models cannot write evidence)
  → deterministic receipt/contradiction checks
  → independent reviewer
  → human Signal decision
  → sourced Story/Brief gate
  → human publish/send
```

Rules:

1. The maker does not grade itself.
2. Deterministic checks run before model judgment.
3. Every loop has a trigger, measurable goal, durable state, bounded retries, evidence output and a
   stopping condition.
4. Models receive minimized sealed packets, never service-role keys or unrestricted database access.
5. Grok/open-web research stays separate from official public-record evidence.
6. Missing joins remain missing; models do not “complete” an identity.
7. No narrative auto-publishes. Named human approval and correction/version history remain final.

## Later audit checklist — not tonight's priority

For every Grok agent and Claude connector/task, record:

- account/project and exact name;
- enabled/paused state and schedule;
- full prompt/instructions and model;
- folders, connectors, browser/computer/database access;
- allowed write targets and stored credentials;
- last ten outcomes, errors and files/rows changed;
- retry and stop behavior;
- whether a different production job already owns the same responsibility; and
- keep / rewrite / pause / delete decision with rollback.

Do the inventory read-only first. Pause duplicate writers before changing code. Delete only after
the replacement has proven ownership and rollback is documented.
