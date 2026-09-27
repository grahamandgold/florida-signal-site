# Runtime boundary follow-up

Conflicting `status` and `review_status` fields now fail closed: every supplied
status must affirm approval before either public story adapter accepts a row.
A previous approval timestamp cannot overrule an explicit hold in another field.

Verified Clerk health no longer substitutes the aggregate dashboard's refresh
clock for an unavailable authoritative collector receipt. Dashboard freshness is
still reported independently; failed Clerk reads retain their explicit errors.

Validation: the existing unit suite plus regression cases for both public adapters
and timed-out Clerk reads with a fresh dashboard. Production installation and live
verification are separate receipts, recorded in the private engine handoff.
