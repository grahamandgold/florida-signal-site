# Florida Signal — remaining work register

**Historical July 28, 2026 register · not current launch authority**

Current authority: [`SYSTEM_STATE_2026-08-11.md`](SYSTEM_STATE_2026-08-11.md). Completed live
editorial-loop work and recovery steps: [`EDITORIAL_LOOP_RUNBOOK.md`](EDITORIAL_LOOP_RUNBOOK.md).

This register contains unresolved work only. Completed history belongs in dated incident
notes and pull requests.

## P0 — requires Andy's decision

### Decide how to contain the public preview

GitHub Pages currently serves `thefloridasignal.com`, even though the product is not
approved for launch. Choose one explicit state:

1. unpublish GitHub Pages;
2. replace the public build with a minimal `noindex` holding page; or
3. knowingly keep the preview public while launch work continues.

Do not change Pages, DNS, or the public build without that decision.

## P0 — launch blockers

- Configure and verify the intended production API hostname and TLS. It currently has no DNS
  answer.
- Prove authenticated CMS, subscriber signup, Mailchimp handoff, agenda recon, and data-health
  behavior end to end against the production topology.
- Remove public indexing permission until launch approval, if the chosen preview policy
  requires containment.
- Review the now-reconciled site PR #4 diff. Its conflicts are resolved, the public-API
  files from `main` are retained, and the PR is mergeable; it still requires explicit review
  and approval before merge.
- Review PR #3 and PR #4 independently. Do not combine, merge, or deploy them by implication.
- Run a full release checklist from a named commit, record the evidence, and obtain Andy's
  explicit launch approval.

## P1 — operations and resilience

- Perform and document a restore drill from the off-site artifact whose hardened
  `QUICK_CHECK=ok` verification passed on July 28.
- Monitor the next automatic Sunbiz cycle and verify that no
  `source='sunbiz-web-search' AND match_type='ERROR'` rows return.
- Keep Acclaim browser-gate failures visible and non-blocking; decide whether its residential
  dependency can be moved off the Mac.
- Keep the parcel timer disabled unless a new folio-enrichment requirement is approved.
- Reconcile the public site freshness UI with authoritative feed-specific states, including
  official-source staleness.
- Audit current consumers and intended grants for Supabase's pre-existing
  `SECURITY DEFINER` view/function findings before changing permissions or behavior.
- Define the approved Drive retention policy before enabling automatic deletion.

## P1 — product systems

- Decide the production CMS storage/authentication model.
- Complete Mailchimp production credentials, audience mapping, consent text, double-opt-in,
  failure handling, and evidence of a test subscription.
- Complete the meeting and agenda automation path with source links and visible failure
  states.
- Replace any preview-only copy or unverified numeric claim before launch.

## P2 — documentation maintenance

- Keep [`SYSTEM_STATE_2026-07-28.md`](SYSTEM_STATE_2026-07-28.md) and the Google Drive
  launch-truth document synchronized after material operational changes.
- Add a historical/superseded banner to any older handoff that is still likely to be used as
  a front door; do not rewrite historical evidence into present tense.
- Record branch, deployment, DNS, service, backup-integrity and source-health evidence in
  each future checkpoint.
