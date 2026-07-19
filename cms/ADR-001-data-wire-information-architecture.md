# ADR-001: The Data Wire information architecture

**Status:** Accepted
**Date:** 2026-07-19
**Deciders:** Andy (Florida Signal / Graham & Gold LLC)

## Context

The Data Wire has grown one page at a time and now has three surfaces that were each built for a
different task, at a different time, with no shared shell:

| Surface | Purpose | How you reach it today |
|---|---|---|
| `index.html` | Draft, gate and clear editorial packets (SQLite) | The desk root |
| `data.html` | Read-only viewer over the whole Supabase intelligence store | One text link buried in a privacy note |
| `review.html` | Approve/hold/reject candidate Signals (Supabase queue) | Nothing links to it at all |

Three problems follow from that:

1. **No wayfinding.** Nothing on `data.html` links back to the desk, and nothing anywhere links to
   `review.html`. Someone who did not build these pages cannot discover two of the three.
2. **No stated mental model.** All three deal with "records", so the difference between *looking at
   data*, *deciding on a Signal*, and *writing a packet* is invisible. That ambiguity is what makes
   the desk feel like a pile of tools rather than a product.
3. **Inconsistent shell.** `index.html` and `data.html` share a palette and a masthead;
   `review.html` was written standalone with its own tokens and type scale, so it reads as a
   different product.

Constraints that shape the answer:

- Local-only, single operator, loopback server. No routing framework, no build step, no bundler.
- Three different data stores are legitimately in play (SQLite packets, Supabase intelligence,
  Supabase review queue). Merging the stores is not on the table in this checkpoint.
- The editorial gate must stay visible: approving is a decision, publishing is a separate act.
- No broad redesign. Navigation and shell only.

## Decision

Adopt a **three-stage pipeline** as the desk's mental model, and give every page the same shell that
names the stage it belongs to:

```
   LOOK                     DECIDE                    WRITE
   Data Desk        →       Signal Review      →      Editorial Desk
   data.html                review.html               index.html
   Read-only. Every         Candidate Signals.        Packets a human
   source, raw.             Approve / hold /          writes, sources
   Explains what is         reject / needs more       and clears for
   and is not mappable.     reporting.                publication.
```

Concretely:

1. One shared `desk-nav` component on all three pages: The Data Wire lockup, the three stages as
   tabs with the current one marked `aria-current`, and a one-line description of the stage.
2. Each stage states its own scope and its own gate in a single sentence, so the three surfaces are
   distinguishable at a glance rather than by memory.
3. `review.html` is rebuilt on the existing desk tokens and type scale so the three pages read as
   one product.
4. Stage order is fixed and shown in order — look, then decide, then write. That is the actual
   editorial workflow, so navigation teaches the workflow.

## Options considered

### Option A — Shared nav across three separate pages *(chosen)*

| Dimension | Assessment |
|---|---|
| Complexity | Low — one header block, no framework |
| Cost | Hours |
| Scalability | Fine to ~6 stages; a fourth store would still just be a tab |
| Team familiarity | Plain HTML/CSS, identical to what already exists |

**Pros:** No build step. Each page keeps its own data client, so a Supabase outage cannot take the
SQLite packet desk down with it. Cheap to add a stage later. Matches how the operator actually
works — a stage at a time, often in separate windows.
**Cons:** The header is duplicated in three files, so a change means three edits. Each page reloads
fully when switching stages.

### Option B — Single-page desk with client-side tabs

| Dimension | Assessment |
|---|---|
| Complexity | Medium — one page owning three data clients and three view states |
| Cost | Days |
| Scalability | Degrades: every new surface grows one file |
| Team familiarity | Fine, but a big rewrite of working code |

**Pros:** One header, one auth prompt, instant stage switching, no reload.
**Cons:** Couples three unrelated stores into one failure domain. Rewrites two pages that currently
work. Directly conflicts with the standing "no broad redesign" constraint.

### Option C — Server-rendered shared layout (Jinja or similar in `server.py`)

| Dimension | Assessment |
|---|---|
| Complexity | Medium — adds a templating dependency and a render path |
| Cost | Days |
| Scalability | Good |
| Team familiarity | Moderate; the server is currently a plain `SimpleHTTPRequestHandler` |

**Pros:** Header defined once, genuinely DRY.
**Cons:** Introduces a dependency and a template layer to a deliberately dependency-free local
server, for three pages. The duplication being solved is roughly twenty lines of markup.

## Trade-off analysis

The real trade-off is **duplication versus coupling**. Option C removes the duplication but adds a
templating layer to a server whose whole virtue is that it has no dependencies. Option B removes
both the duplication and the page reloads, but pays for it by putting three independent data stores
into one failure domain and by rewriting code that already works — the exact kind of churn the
current constraints forbid.

Option A accepts twenty duplicated lines in exchange for keeping the surfaces independent. Given one
operator, three pages, and a stated ban on broad redesigns, twenty duplicated lines is the cheaper
liability. It is also trivially reversible: if a fourth or fifth stage appears, promoting the header
to Option C is a contained change.

## Consequences

**Easier**
- Every surface is reachable from every other surface.
- The pipeline is legible: what each stage is for, and what it will not do.
- The editorial gate is restated on the deciding stage, where it matters.
- Stage failures stay isolated — Supabase being unreachable does not break the packet desk.

**Harder**
- Nav changes require editing three files. Mitigated by keeping the block small and identical, and
  by this ADR recording where it lives.
- Switching stages is a full page load, so each page re-authenticates from the local session
  endpoint.

**To revisit**
- If a fourth stage appears, move the header to Option C rather than editing four files.
- The Data Desk and Signal Review both read Supabase with different credentials (anon key in the
  browser versus service role proxied through the server). That split is correct but is worth
  re-examining if the desk is ever hosted off loopback.

## Action items

1. [x] Add the shared `desk-nav` block to `index.html`, `data.html`, `review.html`
2. [x] Rebuild `review.html` on the existing desk tokens and type scale
3. [x] State each stage's scope and gate in one line on the stage itself
4. [ ] Re-evaluate against Option C if a fourth stage is added
5. [ ] Revisit the credential split before any non-loopback hosting
