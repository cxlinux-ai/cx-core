# BLOCKERS

- **B1 (soft):** First paying user not yet completed — checkout path PASS in e2e; waiting on Michael (or designee) to pay $20 at https://cxlinux.com/pricing (NEEDS_MIKE M1).
- **B2:** Post-pay license activation runtime **unverified** until M1 done.
- **B3:** Full `apt-get install` in ubuntu:24.04/debian:12 containers **unverified** (no docker on box); artifact+CLI path PASS.
- **B4:** `cx-core` dormant since 2026-05-01; ~13 open PRs aging — not blocking first $, blocks trust.
- **B5:** Stripe connector shows legacy Cortex products `active:false`; live checkout still works as CX Core+.

- [RESOLVED 08:52 MT, Michael granted access] 2026-10-19 08:40 MT | B-GH: Cursor cloud agents can't see github.com/cxlinux-ai repos ("not accessible to the connected GitHub account"). Blocks T03/T04/T05 and all repo work. Asked Michael in chat to grant Cursor's GitHub app access to the cxlinux-ai org. Meanwhile: non-repo work (drafts, launch copy, docs).
    10|
- 2026-10-19 09:07 MT | B-DEB: Debian 12 public apt fails (glibc). PARTIAL 09:37: minimal CLI deb builds+runs on Bookworm; full GUI deb build flakes (freetype/zlib). Needs fix + a Bookworm package published (Michael-only release).
- 2026-10-19 09:07 MT | B-ACT: license activation broken on published deb until #774 lands + new APT publish (Michael-only: merge + release).
- 2026-10-20 09:15 MT | B-ACT update: #771/#772 merged; #774 now conflicts with main (rebase agent bc-f3dbaed4 running). Still needs merge + APT publish (Michael-only).
- 2026-10-20 09:15 MT | B-CI: cx-core main `build` fails (debian11 apt 404) and CLA bot rejects cursoragent; fix is draft #776, needs Michael's merge.
- 2026-10-20 09:15 MT | Note: box gh CLI token invalid (401); built-in GitHub tools work, so not blocking.
- 2026-10-21 9:15 MT | B-SANDBOX: #775 sandbox breaks `sudo apt install` (firejail/bwrap) and bwrap discards writes (per REVIEW_775.md on #779; being reproduced + fixed by cloud agent bc-7d5d09f5). Blocks the "sandboxed" marketing claim and #775 merge, not first $.
- 2026-10-21 9:15 MT | B-CI update: #776 now 20/20 green (incl. CodeQL) after #778; main `build` still red (debian11) until #776 merges (Michael-only).
- 2026-10-22 9:15 MT | B-INSTALL: live install.sh installs unrelated npm `cx-cli` (macOS/non-Debian) and fakes success on Debian 12. Fix = cx-web #62 into #60, then merge #60 (Michael-only; merge deploys the site).
- 2026-10-22 9:15 MT | B-AIEXEC: per #780, real AI answers weren't executed/rendered; #775's gate needs #780's parser. Blocks the "dry-run gate works with real AI" claim, not first $.
    20|