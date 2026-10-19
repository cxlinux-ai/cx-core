# docs/autonomy — index

Two autonomous runs are working the CX Linux week of **2026-10-19 → 2026-10-26** under the same mandate. Each keeps its own working docs so neither overwrites the other.

| Track | Focus | Docs |
|---|---|---|
| **Linus** (Cursor-driven) | First paying user: checkout, license activation, install smoke tests, cx-web fixes | `PLAN.md`, `DECISIONS.md`, `BLOCKERS.md`, `NEEDS_MIKE.md`, `LOG.md` in this folder (mirrored from its canonical copies) |
| **Claude** (claude.ai CX Linux project) | cx-core build health and execution safety, bounty ledger, real-diff PR reviews, contributor fairness | [`claude/`](claude/) — `PLAN.md`, `DECISIONS.md`, `BLOCKERS.md`, `NEEDS_MIKE.md`, `LOG.md` |

Shared references:
- [`BOUNTY_AUDIT.md`](BOUNTY_AUDIT.md) — bounty ledger, owed payouts, compliance and FCFS conflicts (live `gh` data)
- [`PR_REVIEWS.md`](PR_REVIEWS.md) — open contributor PR reviews written from the actual diffs

Both tracks agree on the critical path: merge [#771](https://github.com/cxlinux-ai/cx-core/pull/771) (public build) → [#772](https://github.com/cxlinux-ai/cx-core/pull/772) (no auto-execute on EOF) → [#774](https://github.com/cxlinux-ai/cx-core/pull/774) (license activation + install smoke), then publish a new APT package.
