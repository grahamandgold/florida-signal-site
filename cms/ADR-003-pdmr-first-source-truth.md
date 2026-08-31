# ADR-003: PDMR-first private discovery with source-truth states

**Status:** Accepted locally; pushed, not deployed  
**Date:** 2026-08-30  
**Deciders:** Florida Signal product and editorial desk

## Context

The private Data Explorer previously led with later execution/ownership sources and could present a
readable table as simply connected. That hid the distinction between availability, collector
freshness, automation mode and detector coverage. Preliminary and verified Clerk cards also shared
one component receipt, while PDMR and planned earlier sensors were not visible in their intended
research order.

## Decision

1. Lead the private discovery sequence with Fort Lauderdale Preliminary Development Meeting Request
   (PDMR) planning-intent records. Keep permits in the later execution group.
2. Default the table to the bounded, paged, read-only PDMR evidence index.
3. Show sewer/utility, engineering intake, assemblage + new LLC, lobbying and SFWMD as research or
   planned until each has a collector and evidence contract. A file-only shadow collector or
   SQLite view is not a connected Desk lane.
4. Report table availability, source freshness, refresh mode and detector coverage independently.
   A readable automated table without an independent health receipt says `health unknown`; it does
   not borrow a receipt from a related source.
5. Bind preliminary Clerk and verified Clerk to their own public receipts.
6. Treat the 27 studied PDMR records as public. “Frozen” describes the fixed research roster and
   adjudication, not access control; historical first-public timing remains unresolved.
7. Keep public Data Room ordering map-first. PDMR-first is a private Newsroom research decision.

## Consequences

- The desk is honest about what exists, what is fresh, what is automated and what is merely planned.
- A stopped collector cannot remain green because another table is readable or a related source is
  current.
- The private sequence better reflects early discovery without claiming PDMR is a validated winning
  detector or a production feed.
- Production source onboarding, security hardening and deployment remain separate approval gates.

## Verification

- Python tests cover project-state failure behavior, PDMR paging and distinct public receipts.
- Browser tests cover PDMR-first order, live local rows, planned-source labels, keyboard-accessible
  detail drawers, independent unknown-health labels and mobile layout.
- The Finder app is rebuilt from the pushed site branch and tested at `http://127.0.0.1:8788`.

