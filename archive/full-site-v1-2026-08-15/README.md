# Florida Signal full-site preservation point

The complete Florida Signal research site was preserved before the newsletter landing page became the root front door.

- Preserved public route: `/fort-lauderdale/`
- Permanent Git tag: `full-site-v1-pre-newsletter-root-2026-08-15`
- Tagged commit: `bc8c62e`
- Root behavior at the tag: `/` forwarded readers to `/fort-lauderdale/`
- New launch behavior: `/` presents the Florida Signal Brief; the research site remains available at `/fort-lauderdale/`

This is a routing and launch-priority change, not a deletion. The research pages, assets, diagrams, data interfaces, methods and source links remain in their existing directories.

## Recovery

To inspect the preserved version without changing the active branch:

```sh
git show full-site-v1-pre-newsletter-root-2026-08-15:index.html
git worktree add /tmp/florida-signal-full-site-v1 full-site-v1-pre-newsletter-root-2026-08-15
```

Do not move the full site back to `/` without an explicit rollout decision. New research features can continue to ship under `/fort-lauderdale/` while the newsletter front door is tested and refined.
