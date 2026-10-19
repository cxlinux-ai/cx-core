# BLOCKERS

- **B1 (soft):** First paying user not yet completed — checkout path PASS in e2e; waiting on Michael (or designee) to pay $20 at https://cxlinux.com/pricing (NEEDS_MIKE M1).
- **B2:** Post-pay license activation runtime **unverified** until M1 done.
- **B3:** Full `apt-get install` in ubuntu:24.04/debian:12 containers **unverified** (no docker on box); artifact+CLI path PASS.
- **B4:** `cx-core` dormant since 2026-05-01; ~13 open PRs aging — not blocking first $, blocks trust.
- **B5:** Stripe connector shows legacy Cortex products `active:false`; live checkout still works as CX Core+.

- [RESOLVED 08:52 MT, Michael granted access] 2026-10-19 08:40 MT | B-GH: Cursor cloud agents can't see github.com/cxlinux-ai repos ("not accessible to the connected GitHub account"). Blocks T03/T04/T05 and all repo work. Asked Michael in chat to grant Cursor's GitHub app access to the cxlinux-ai org. Meanwhile: non-repo work (drafts, launch copy, docs).

- 2026-10-19 09:07 MT | B-DEB: no Debian 12 install (deb needs libc6>=2.39). Working on a Bookworm build in PR #774 follow-up.
- 2026-10-19 09:07 MT | B-ACT: license activation broken on published deb until #774 lands + new APT publish (Michael-only: merge + release).
