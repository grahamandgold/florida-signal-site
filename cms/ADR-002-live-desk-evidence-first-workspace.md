# ADR-002: Live Desk evidence-first workspace

**Status:** Accepted
**Date:** 2026-08-12
**Deciders:** Florida Signal product and editorial desk

## Context

The original three-tab information architecture made the private pages reachable, but it did not
solve the operator's main problem: hundreds of expanded candidates, inconsistent mastheads, no
continuous view of pipeline state, and research tools separated from the Candidate being judged.
It also treated navigation markup as intentionally duplicated even after the workspace grew to a
fourth surface.

## Decision

Use a shared dependency-free shell and a continuous **Live Desk** home:

1. **Live Desk** shows current queue state and the next useful action.
2. **Explore** is an exact, indexed record lookup with explicit source clocks.
3. **Review** presents one Candidate at a time, with evidence open before decision controls.
4. **Write** assembles a separately gated Story Packet.

The approved Florida Signal emblem is the only mark in the shell and always links Home. The shell
also reads the production host's upcoming systemd timers through an authenticated, read-only local
endpoint. Timer time is schedule evidence only; source event and collection clocks remain the
freshness authority.

Live Desk is explicitly multi-source and ordered by how early a clue can appear: zoning/planning
meetings and agenda packets; company formation and principals; ownership, deeds, financing and
liens; environmental and airspace filings; then permit applications and inspections. Permits are
execution evidence, not the product definition. A monitored source lane is not called a working
detector until it produces a source-sealed Candidate packet.

Agenda intelligence requires the packet and attachments, not merely a calendar row. The durable
target is to preserve the original PDF and attachments, hash them, extract item/page citations,
addresses, folios, applicant/agent names, proposed actions, conditions, staff recommendations and
embedded rendering/image references. OCR or model output remains private until checked against the
cited page. Renderings are attachments/evidence with attribution, never proof that a proposal was
approved or will be built.

Review follows Record → Candidate → Signal → Story. A Candidate cannot be approved without a
non-empty evidence packet and server-side evidence receipt. Approval records a desk decision and
publishes nothing. Mobile supports research, hold, more-reporting and skip; irreversible approve and
reject controls remain desktop-only.

Each Candidate includes an Investigation Kit derived from its exact permit record:

- Street View, satellite and Maps use latitude/longitude without changing source evidence.
- parcel search opens the internal exact lookup;
- Google News and direct Sunbiz search are discovery tools;
- Grok receives a copied public-record research brief and is explicitly treated as a lead generator,
  never as evidence.

Useful external results must be opened, dated, source-linked and added to the evidence packet before
they support a claim. Similar names or addresses never create an identity join. The current empty
Sunbiz public table is shown as a blocking gap.

## Consequences

- The operator sees one next action and one Candidate instead of a full database dump.
- Navigation, branding and timer context remain consistent across pages.
- Exact search avoids the former leading-wildcard timeout path.
- Production SSH availability affects only the schedule strip. When unavailable, the desk reports
  the schedule as unavailable and infers no job status.
- External research remains a manual lead-gathering step until an auditable provider integration,
  cost controls and citation persistence are implemented.

## Verification

- Unit tests cover indexed queue defaults, exact permit context and fail-closed timer parsing.
- A mobile browser check covers research links, hidden irreversible decisions and horizontal fit.
- Production queue readiness is stored and indexed in Supabase; blocked Candidates cannot pass the
  server's approval check.
