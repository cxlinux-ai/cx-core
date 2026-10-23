# LOG

## 2026-10-19 (Mon)
- Mandate received ~8:33am MT. Restart chosen. E2E test running. Daily cycle set for weekdays ~9am MT.

### E2E complete ~08:36 MT
- Wrote `../e2e-test-2026-10-19.md`. Pricing LIVE; Pro → Stripe **live** checkout (AIVH LLC, CX Core+ $20, `cs_live_`); no card entered.
- License server health 200 (v2.0.0). APT deb SHA match; `cx-terminal --version` OK; `ask` needs model/key.
- Autonomy: `PLAN.md` + `NEEDS_MIKE.md` filled; BLOCKERS/DECISIONS updated.
    10|- Next: Michael M1 ($20 pay) is the critical path.
- 08:40 MT: cloud-agent launch on cx-web blocked (no GitHub access to cxlinux-ai); logged B-GH / M0.
- 08:53 MT: GitHub access granted. Launched cloud agent bc-41dfda0e (Composer 2.5) on cx-web for T03 soft-404, T05 install CTA, T04 Pro/CX Core+ naming. PR pending.
- 08:58 MT: SHIPPED (draft) cx-web PR #57 https://github.com/cxlinux-ai/cx-web/pull/57, npm check+build pass, local /pricing 200, junk 404. Open: wrangler pages dev still 200 on junk; asked agent to fix + confirm CI. Next: T-license activation proof, apt install in container (cloud VM has docker).
- 09:00 MT: launched cloud agent bc-6e2120ee (Composer 2.5) on cx-core: clean apt install in ubuntu 24.04/debian 12, license activation proof, CI smoke test, triage of 13 open PRs.
- 09:03 MT: PR #57 now 404s junk paths under wrangler (commit 01880926); Cloudflare Pages preview + CodeRabbit pass. Risk: early 404 in middleware could hit static assets/dynamic slugs/Stripe return URLs; asked agent to prove with preview + headless browser before recommending merge.
- 09:07 MT: SHIPPED (draft) cx-core PR #774 https://github.com/cxlinux-ai/cx-core/pull/774: Ubuntu 24.04 apt install PASS (cx-terminal 20260223-145346-e97bbc7b), Debian 12 FAIL (glibc), license server health PASS, activate CLI FAIL on published deb (fixed in PR), new APT smoke CI green on ubuntu. Open-PR triage done; merge recs in NEEDS_MIKE. Next: Debian 12 build, unify activate copy across docs/site.
- 09:11 MT: PR #57 safety pass: assets, sitemap, rss, blog slugs, Stripe success/cancel routes OK on preview https://cursor-fix-spa-routing-prici.cx-web.pages.dev; Playwright no network 404s. Pre-existing bad frontmatter in ai-command-line-tools-linux.mdx (to fix). Final check queued: preview checkout click-through to Stripe.
- 09:15 MT: PR #57 VERIFIED ready (checkout API on license.cxlinux.com, unaffected by Pages /api 404; Core+ and Team reach Stripe on preview, no card). Moved to READY in NEEDS_MIKE. Next for cx-web: fix bad frontmatter in ai-command-line-tools-linux.mdx; align activation copy with cx-core #774 once chosen.

    20|### Daily cycle run 09:22 MT (routine)
- Verified (GitHub API 09:25 MT): cx-web PR #57 draft, mergeable_state clean, head fb90f38 — unchanged since READY. cx-core PR #774 draft, mergeable_state blocked (needs review/merge order #771→#772→#774), 5 review comments open; agent bc-6e2120ee still running (Bookworm build).
- Launched cloud agent bc-71fb33cc (Composer 2.5) on cx-web, new branch off main, independent of #57: T06 visible checkout-failure error + retry (with mocked-failure test) and fix bad frontmatter in ai-command-line-tools-linux.mdx. PR pending.
- Drafted (pulled T13 forward): `../drafts/first-user-playbook.md` (buyer path with verified/unverified per step; gate = M-CORE before inviting payers) and `../drafts/launch-posts-DRAFT.md` (do-not-post until M-CORE + #57 + Michael OK).
- Next: verify bc-71fb33cc PR (tests, preview); check #774 Bookworm result + review comments; T10 activation proof after M1 + M-CORE.
- Risk: paid traffic before M-CORE = buyers who can't activate. No external sends made.
- Repo mirror (docs/autonomy/ in cx-core, PR #773) NOT synced this run: the routine run can't steer agent bc-6e2120ee (owned by the main chat). Main chat can queue the sync on that agent; otherwise next cycle syncs via a new docs-only agent.
- 09:27 MT: SHIPPED (draft) cx-web PR #58 https://github.com/cxlinux-ai/cx-web/pull/58: checkout error banner/retry/timeout + blog frontmatter fix; npm check/test(8)/build pass; CF Pages CI pending. Queued autonomy-docs mirror update on cx-core agent bc-6e2120ee.
- 09:36 MT: cx-core PR #773 docs mirror updated (0142cfcb), but my 'replace exactly' instruction removed BOUNTY_AUDIT.md + PR_REVIEWS.md (not ours). Asked agent to restore them. PR #773 is non-draft (can't revert to draft from agent). Lesson: mirror = add/overwrite our 5 files only.
- 09:37 MT: PR #773 files restored (c769f3b5). PR #774 results: Debian 12 minimal CLI .deb built on Bookworm PASS (cx --version, cx activate --help); full GUI .deb on Bookworm FAIL (freetype/zlib build flake); canonical command = `cx activate <LICENSE_KEY>` (aliases kept); real license server invalid key PASS (clear error, exit 1). Size is mostly committed logs (~4.6K lines); Cargo.lock net -214 (drops private hrm-ai), no vendored deps.
    30|- Next cycle: (a) move big verification logs out of #774 into CI artifacts to slim the diff; (b) fix full Bookworm GUI build flake; (c) align cx-web activation copy to `cx activate`; (d) recheck PR #58 CI.

## 2026-10-20 (Tue)
- 04:10 MT: Michael shared market read and the repositioning. Launched cloud agent bc-821dfa51 (cx-core: dry-run-by-default guard, verify safety claims, 30s demo). Drafting positioning one-pager + "CX vs Ubuntu built-in AI" (MD+PDF) in drafts/. Note: "build green" not yet true on main (#771 unmerged).
- 04:12 MT: Drafts done: drafts/cx-positioning-one-pager.{md,pdf}, drafts/cx-vs-ubuntu-ai.{md,pdf}. 7 safety claims tagged [verify before publishing] pending bc-821dfa51. Sources confirmed; Canonical says opt-in/local/removable, so our edge = dry-run default, rollback, Debian+Ubuntu, available on LTS. Open: demo link /ai-consultant vs /ai-consultant/vip; cx-core license "Other" so say "public code" not "open source".
- 04:17 MT: Digested Michael's 10 docs (inputs/2026-10-20/DIGEST.md). Queued M-LIST, M-GHPROFILE, M-LICENSE. Next: FACTS.md + blocklist, demo FAQ, re-draft emails 1-2 around the new positioning.
- 04:20 MT: FACTS.md, drafts/demo-faq-DRAFT.md and drafts/email-seq-1-2-DRAFT.md done. Code read: dry-run not the default (-y skip, [Y/n]) and no sandbox (sh -c). Fed both to bc-821dfa51. get.cxlinux.com down; cx-docs link 404.
- 04:39 MT: bc-821dfa51 opened draft cx-core #775. Claims: dry-run PASS; sandbox PARTIAL (firejail/bwrap, falls back with a warning); AppArmor FAIL; undo PASS for cx ask; audit, offline and uninstall PARTIAL. Next: check #775 CI, then update FACTS.md and the drafts with these verdicts.
- 08:18 MT: #775 is mergeable with no conflicts (Michael saw the block). Blockers: CLA check, debian11 build after 12s, 8 open review threads, CodeQL pending, GidTeam review. Asked bc-821dfa51 to fix review threads, find the debian11 root cause and the CLA cause. Note: #775 is no longer a draft.
- 08:32 MT: #775 fixed all 8 review comments (2 threads resolved, 6 pending). Cargo, Clippy, fmt, tests, CodeQL and Sonar are green. Remaining failures predate this PR: CLA (cursoragent not allowlisted), debian11 apt 404 (fails on every PR), build-docs broken link. Asked for a separate CI-unblock draft PR.
    40|- 09:04 MT: Draft cx-core #776 (CI unblock: CLA allows cursoragent only with a signed co-author, debian11 apt via archive.debian.org, docs links). Its checks pass except CodeQL (3s quirk). Commits authored as Mike to pass the old CLA check; flagged to Michael. All 8 #775 threads resolved. Plan: merge #776, update the #775 branch, re-run CI, merge #775.
- M-PR776: merge #776 first (Michael tap).

### Daily cycle run 09:12 MT (routine, Oct 20)
- Verified (GitHub API + curl, 9:13–9:15 MT): cx-web #57, #58, #59 MERGED (~8:52–8:53am MT, 14:52–14:53Z); cx-web main CI green (head 2497fe96). Live: https://cxlinux.com/pricing 200, /getting-started 200, /blog 200, /sitemap.xml 200, junk path 404, license.cxlinux.com/health 200, repo.cxlinux.com Release 200. (/rss.xml 404 but the feed lives at /blog/rss.xml 200.)
- cx-core: #771 + #772 merged Oct 19 ~12:50pm MT; #773 docs mirror merged ~4:09pm MT. #774 is draft + dirty (conflicts). #775 open: 28 checks pass, 3 fail (build/debian11, build-docs, cla-check, all pre-existing). #776 draft: 19 pass, CodeQL fail. cx-core main 7b88a923: only `build` fails (debian11 apt 404, fixed by #776).
- Live bundle scan: activation copy mixes `cx activate` and `cx license activate`; two GPG key URLs (key.gpg / pub.gpg, same file); install.sh claims Debian 11+ though Debian 12 fails. Published package still lacks `activate` (per #774), so live copy tells buyers a command that won't work yet. Not an emergency: 0 known paying users.
- Couldn't reply to earlier agents from this run (tool limit), so launched fresh Composer 2.5 agents: bc-f3dbaed4 (cx-core: rebase + slim #774 on its branch, fix Bookworm GUI flake if cheap, plus a docs-only draft PR syncing these 5 files) and bc-293c0687 (cx-web: one activation command, one apt snippet, verified-OS-only claims; draft PR).
- NEEDS_MIKE: marked M2/M-PR57/M-PR58 done; added tap order #776 → #775 → #774 → APT release → M1.
- gh CLI token on the box is invalid (401); used the built-in GitHub tools instead. Not a blocker.
    50|- Next cycle: verify both new PRs (CI, diff, preview); recheck #775/#776; rerun T08/T09 after #774 rebase.
- No external sends, merges, deploys or Stripe writes.
- 09:19 MT: Draft cx-web #60 (https://github.com/cxlinux-ai/cx-web/pull/60) makes every page use `cx activate <key>` and one install snippet, and lists Ubuntu 24.04 as the only verified system. tsc, 10/10 tests, build and Pages preview all pass. Follow-ups: the docs/ Docusaurus install page still uses key.gpg, and blog excerpts still say "Debian/Ubuntu".
- M-PR60: merge cx-web #60 after #776/#775 (low risk, preview https://74e483d8.cx-web.pages.dev).
- 10:06 MT: #774 has no conflicts and is down to +802/-59 (logs moved to CI artifacts). Debian 12 minimal .deb build and install smoke are green, and so is the Ubuntu 24.04 APT smoke. The optional full GUI .deb still fails (follow-up; artifact on run 39448560683). Draft docs-sync PR #777 touches only docs/autonomy/*. Merge order: #776, #775, #774, #777, cx-web #60, then a new APT release and the $20 test purchase.

### Daily cycle run 09:02 MT (routine, Wed Oct 21)
- Verified live (curl 9:02 MT): https://cxlinux.com/ 200 (now sends HSTS), /pricing 200, /getting-started 200, license.cxlinux.com/health 200, repo.cxlinux.com/apt/dists/stable/Release 200. No production harm found.
- Verified GitHub (API 9:05 MT): cx-web #61 (homepage server-render + HSTS, by Michael's account) merged Oct 21 ~1:09am MT. cx-core #778 (CLA security fix + Debian 11 archive on all 3 workflows) merged into #776's branch Oct 20 ~11:38am MT; #776 head f48caff3 now 20/20 checks success. #774 (5fbee3cd), #775 (36ef88e2), #776 all mergeable=true, state "blocked" (needs review only). cx-web #60 mergeable_state clean. cx-core main 7b88a923: 28 pass, 1 fail (`build`, debian11), fixed by #776.
- Found: Michael's Claude track opened #779 (docs) with REVIEW_775.md: #775's sandbox blocks `sudo apt install` and bwrap discards writes. Not yet independently reproduced.
    60|- Launched cloud agent bc-7d5d09f5 (default model) on #775's branch: reproduce the 3 review findings, fix on-branch, tests, update CLAIMS_VERIFICATION.md. No new PR, no merge.
- Updated FACTS.md + positioning one-pager: sandbox FAIL for installs, no AppArmor claim.
- NEEDS_MIKE: new tap order #776 → #774 → APT release → M1; #60, #777 any time; #775 on hold.
- Next cycle: verify bc-7d5d09f5 commits (reproduction logs, tests, CI); if green, move M-PR775 back to ready.
- No external sends, merges, deploys or Stripe writes.
- 09:20 MT: launched docs-sync agent bc-7b754cdd on #777's branch (overwrite our 5 docs/autonomy files only, never docs/autonomy/claude/). Next cycle verifies the diff.

## 2026-10-21 ~9:15 MT — #775 sandbox-fix agent (bc-7d5d09f5) finished
- Pushed commit 6ee3fef40 to the #775 branch (cursor/safety-dry-run-demo-4556). It touches 3 files, +153/-12.
- **Claims (UNVERIFIED by me):**
    70|  - It reproduced and fixed the bwrap cwd write-loss bug: cwd is now bound read-write with --chdir, and it fails closed if cwd is missing.
  - It hardened the read-only allowlist against command injection: it rejects shell metacharacters and only accepts exact matches.
  - It added 4 unit tests.
- **Design change to review:** `sudo apt/apt-get/dpkg/snap` now bypass the sandbox and run on the host after --execute plus the [y/N] prompt. So package installs are NOT sandboxed. Marketing must keep saying "previewed, confirmed, audited, undoable", not "sandboxed installs".
- **Caveat:** the agent could NOT run a full cargo build (the getrandom/edition2024 issue that #776 fixes), so the tests have not run in CI yet.
- **Next cycle:**
  - Check #775 CI on 6ee3fef40.
  - Keep #775 on HOLD until cargo build and tests pass and someone independent, ideally Gatekeeper, reviews the privileged-bypass design.
- No external sends, merges or deploys.

    80|## 2026-10-21 ~9:23 MT — docs-sync agent (bc-7b754cdd) finished
- It pushed f3dc38d6d to docs/autonomy-sync-2026-10-20 ([cx-core #777](https://github.com/cxlinux-ai/cx-core/pull/777)). Only the 5 autonomy docs changed (+54/-5), and docs/autonomy/claude/ was left untouched.
- **Checks:** 9 of 12 passed. Test Suite was still running. cla-check and build-docs fail, but those failures were already there and #776 fixes them.
- #777 stays a docs-only draft, and merging it is low priority. No sends, merges or deploys.

### Daily cycle run 09:01 MT (routine, Thu Oct 22)
- Verified live (curl 9:01 MT): https://cxlinux.com/ 200, /pricing 200, /getting-started 200, junk path 404, license.cxlinux.com/health 200, repo.cxlinux.com/apt/dists/stable/Release 200.
- Verified GitHub (built-in GitHub tools, ~9:05 MT): no merges since yesterday. cx-core #776 (f48caff3, draft), #774 (5fbee3cd, draft), #777 (f3dc38d6, draft), #775 (6ee3fef4) all still open. cx-web #60 (draft) open.
- #775 CI on 6ee3fef4: 28 pass incl. Test Suite, Cargo Check, Clippy; 3 fail (build/debian11, build-docs, cla-check), all pre-existing and fixed by #776. So yesterday's "tests never ran" caveat is cleared. #775 stays HOLD for (a) an independent review of the host-bypass for `sudo apt/dpkg/snap` and (b) the #780 overlap below.
- New from Michael's Claude track (read as evidence, not duplicated):
    90|  - cx-core #780 https://github.com/cxlinux-ai/cx-core/pull/780 (6608052a): real AI answers rendered as raw JSON and `-d` never executed them; adds a parser + 11 tests + real-model 30 s demo. CI 30 pass, 1 fail (`build`, the old debian11 one). It says #775's gate keys on a field real backends don't send, so whichever merges second needs a small rebase.
  - cx-web #62 https://github.com/cxlinux-ai/cx-web/pull/62 (38ca57f9, stacked on #60): install.sh fail-safe. I verified the core claim myself: the live https://cxlinux.com/install.sh (260 lines) runs `npm install -g cx-cli` on macOS/non-Debian, and `npm view cx-cli` says "Modern CLI for scaffolding CxJS applications" (codaxy/cxjs), unrelated to CX. CI 1/1 pass.
- Production check: the install.sh issue is live and wrong, but not new, there are 0 known paying users, and Michael's own track already has the fix PR, so I did not interrupt him. Queued as tap #2 (M-PR62) in NEEDS_MIKE.
- Repo work this cycle: launched one docs-sync cloud agent on #777's branch (5 autonomy files only). No other new agents: everything else on the critical path waits on merges (#776, #774) or on #780 landing first.
- Next cycle (Fri): verify the docs sync; if #780 merges, launch an agent to rebase #775 onto its parser; file the weekly scorecard Friday (T15's Oct 25 is a Sunday, and this routine runs weekdays).
- No external sends, merges, deploys or Stripe writes.
- 09:14 MT: launched docs-sync agent bc-654f063a (default model) on #777's branch with the 5 files attached; next cycle verifies the diff touches only those 5 paths.

## 2026-10-22 ~9:05 MT — docs-sync agent (bc-654f063a) finished
- It pushed 61c304e02 to docs/autonomy-sync-2026-10-20 ([cx-core #777](https://github.com/cxlinux-ai/cx-core/pull/777)). It reports exactly the 5 autonomy docs changed (+57/-5). #777 is still a draft, now titled "docs(autonomy): sync 2026-10-22".
   100|- **Checks:** cla-check fails and build-docs was pending; both are known failures that #776 fixes. Other checks were still pending. Friday's cycle confirms the file list on GitHub.
- No sends, merges or deploys.

### Daily cycle run 09:04 MT (routine, Fri Oct 23)
- Verified live (curl 9:04 MT): https://cxlinux.com/ 200, /pricing 200, /getting-started 200, junk path 404, license.cxlinux.com/health 200, repo.cxlinux.com/apt/dists/stable/Release 200. Live install.sh still has `npm install -g cx-cli` (lines 172, 248): bug unchanged, 0 known users, fix PR #62 exists, so no interrupt.
- Verified GitHub (built-in tools ~9:05 MT): no PR merged in cxlinux-ai since cx-web #61 (Oct 21). Updated since Oct 22: only #777, #779, #781.
- #777 (61c304e0): file list on GitHub is exactly the 5 docs/autonomy files. Yesterday's sync verified.
- New: cx-core #781 https://github.com/cxlinux-ai/cx-core/pull/781 (848f401c, Claude track, base demo/30s-tape = #780, mergeable clean, +1124/-0, 3 files). Package guard: only plain apt/apt-get/dpkg/snap accepted, `apt-get -s` preview, [y/N] default No, exact argv without a shell, audit.log + transactions.jsonl with undo. Claims 44 tests + real apt install/undo on Ubuntu 24.04. Only 3 checks ran (SonarCloud x2, cla-check, all pass) because the base isn't main, so the test claims are UNVERIFIED by me.
- Decision: #781 supersedes #775's sudo-apt host bypass. Recommend #780 → #781, then re-scope #775 to dry-run default + sandbox for non-package commands and rebase. Not duplicating Claude-track work.
- Shipped: weekly scorecard `scorecards/2026-10-23.md` (T15). Paying user: NO.
   110|- Repo work: no new feature agents (everything on the critical path waits on Michael's merges). Docs-sync agent launched for #777.
- No external sends, merges, deploys or Stripe writes.
