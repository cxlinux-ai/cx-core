# Needs Mike — ready to approve

Each item is outside the autonomy limits (money, external communication, or account access). Recommendation first; approving means "do exactly this." Reply with the item number + "approved" and the next run executes it.

| # | Item | Recommendation | Cost / commitment | Why it's queued |
|---|---|---|---|---|
| ~~**N0**~~ | ✅ **DONE 12:50 MT** — Mike merged #771 and #772. ~~**Approve [#771](https://github.com/cxlinux-ai/cx-core/pull/771)** — restores the public build; all 4 required checks + CX Terminal Build (macOS, Ubuntu) pass. The repo ruleset needs 1 approving review and the PR comes from your account, so it can't self-approve | Open the link → **Files changed** → **Review changes** → **Approve** → **Squash and merge**. #772 then retargets to main automatically ~~ | — | — |
| **N1** | **Pay two merged bounties** — cx-distro [#76](https://github.com/cxlinux-ai/cx-distro/pull/76) @silasbrookshaha $25 (merged Oct 10, asked how to claim Oct 11, unanswered) and [#83](https://github.com/cxlinux-ai/cx-distro/pull/83) @Ravikirar $25 (merged Oct 16) | Pay both via tip.cc today and post the drafted thank-you (Appendix A) | **$50** | Spending + public reply |
| **N2** | **Add the post-funding bonus note to 19 non-compliant cx-distro bounty issues** (#27–33, #35–45, #48) | Approve; script in Appendix B edits all 19 in one pass | **+$475 post-funding** commitment | Changes financial terms publicly |
| **N3** | **Post the real-diff reviews** on 11 open PRs (findings in [PR_REVIEWS.md](../PR_REVIEWS.md)) | Approve; Appendix C posts them as "comment" reviews (not approve/merge) | none | Public communication as the company |
| **N4** | **Resolve 4 stale FCFS assignments** — cx-core #425 (@sujay-d07), #428 (@Suyashd999); cx-distro #45, #50 (@Sahilbhatane) — all assigned months ago with no PR from the assignee while outside contributors submitted work | Post a 7-day check-in on each (Appendix D); unassign if no reply by Oct 27, then review the waiting PR on merit | none now | Personnel/assignment decision + public comment |
| **N5** | **Merge cx-distro [#71](https://github.com/cxlinux-ai/cx-distro/pull/71) (Safe NVIDIA installer) after its one rollback fix** | Approve conditional merge; next run requests the fix via N3 and merges when CI is green | **$100** on merge | Pay-on-merge = spending |
| **N6** | **Install the Claude GitHub App on `cxlinux-ai`** so cloud runs can push without your Mac being awake | One click: https://github.com/apps/claude/installations/select_target → choose `cxlinux-ai` → All repositories → Install | none | Account access |
| **N7** | **Update the CX Linux project instructions** — the spec still describes the Python repo, `pytest`, and the legacy install URL. Reality: `cxlinux-ai/cx-core` (Rust), `cargo test -p cx-terminal`, install `curl -fsSL https://cxlinux.com/install.sh \| bash`, APT at `repo.cxlinux.com` | Paste the replacement §16 block in Appendix E into the project Instructions field | none | I can't edit project instructions from here |
| **N8** | **Price or label #708 and #712** before anyone merges [#765](https://github.com/cxlinux-ai/cx-core/pull/765) / [#744](https://github.com/cxlinux-ai/cx-core/pull/744) | Label both `no-bounty` (765 duplicates shipped work; 744 needs a redesign) | none | Sets compensation expectations publicly |

---

## Appendix A — N1 thank-you replies (professional default)

**On cx-distro #76:**
> Thanks @silasbrookshaha — merged and appreciated. Your $25 bounty for #26 has been sent via tip.cc. Sorry for the slow reply on the claim question; going forward bounties are paid within 48 hours of merge.

**On cx-distro #83:**
> Thanks @Ravikirar — merged and appreciated. Your $25 bounty for #34 has been sent via tip.cc.

## Appendix B — N2 script (run on the Mac; edits issue bodies in place)

```bash
for i in 27 28 29 30 31 32 33 35 36 37 38 39 40 41 42 43 44 45 48; do gh issue view $i -R cxlinux-ai/cx-distro --json body --jq .body > /tmp/b$i.md && python3 -c "import re,sys;p=sys.argv[1];s=open(p).read();s2=re.sub(r'(\*\*Bounty:\*\*\s*\\\$(\d+))([^\n]*)',lambda m:m.group(1)+' (+ \$'+m.group(2)+' bonus after funding)'+m.group(3) if 'funding' not in m.group(0).lower() else m.group(0),s,count=1);open(p,'w').write(s2);print(p,'changed' if s2!=s else 'UNCHANGED')" /tmp/b$i.md && gh issue edit $i -R cxlinux-ai/cx-distro --body-file /tmp/b$i.md; done
```

The next autonomous run verifies every issue afterwards and reports any that printed `UNCHANGED` (different bounty wording).

## Appendix C — N3 review posting

Review bodies are the "Findings from the diff" cells in PR_REVIEWS.md, posted verbatim with `gh pr review <n> --comment --body-file`. The next run generates and posts them once N3 is approved.

## Appendix D — N4 check-in text

> Hi @{assignee} — checking in on this one. It's been assigned since {date} and we have a community PR waiting on the same issue. If you're still working on it, reply here within 7 days with a status update or a draft PR and it stays yours. Otherwise we'll reassign on {date+7} so the work can move forward. Thanks for contributing to CX.

## Appendix E — N7 replacement for spec §16 "Repository & workflow"

> **Repository & workflow (verified 2026-10-19):** Canonical org `cxlinux-ai`. Product repo `cxlinux-ai/cx-core` (Rust; WezTerm-based CX Terminal + `cx` CLI; crate `cx-terminal`), main branch `main`. Build `cargo build -p cx-terminal`; test `cargo test -p cx-terminal` (CI: `cargo test --workspace`). Distro/packaging work in `cxlinux-ai/cx-distro`; site in `cxlinux-ai/cx-web`. Install one-liner `curl -fsSL https://cxlinux.com/install.sh | bash`; APT repo `https://repo.cxlinux.com/apt` (key `https://repo.cxlinux.com/key.gpg`). The legacy org and legacy apt host are retired. `gh` patterns use `-R cxlinux-ai/cx-core` or `-R cxlinux-ai/cx-distro`.

## Also new this cycle
- **N9 — CLA check on #773 fails for `@cursoragent`.** The parallel Cursor agent's commits are authored as `cursoragent`, which hasn't signed CLA.md. Recommendation: add `cursoragent` to the CLA allowlist used by `cla-check.yml` (same as other bots), or have its commits authored as you.

## New in cycle 2 (2026-10-19 19:25 MT)
- ~~**N10**~~ ✅ **DONE 2026-10-20** — Claude GitHub App installed; cloud pushes of workflow files work. ~~**Let pushes change CI workflow files (one-time).** The Mac's GitHub login has `repo` but not `workflow` scope, so GitHub refuses any push that edits `.github/workflows/`. The Debian 11 CI fix is committed and waiting (`ci/debian11-archive-security`, patch also saved at `docs/autonomy/claude/patches/p4-debian11.patch`).~~
  - **Browser (recommended, also clears N6):** open https://github.com/apps/claude/installations/select_target → pick **cxlinux-ai** → **All repositories** → **Install**.
  - The next run pushes the branch and opens the PR.
- **N11 — Keep shipping Debian 11 packages?** Debian 11 reached end of life on 2026-08-31 (no more security updates). README still lists it as supported. Recommendation: keep building it this week via the archive fix (zero user impact), and drop it from the supported-platforms table and CI next release. Approve "drop Debian 11" or "keep".

## New on Day 2 (2026-10-20)
- **N16 (top) — Review and merge [#776](https://github.com/cxlinux-ai/cx-core/pull/776)** (now includes #778). It unblocks every open PR's CI: cursoragent CLA allowlist, Debian 11 archive sources on all three workflows, and a docs-build link fix. #778 also **removed a critical security hole #776 had introduced** (CLA workflow running PR-controlled code with a write token). Recommendation: approve → **Squash and merge**. After that: #775, #777 and the Dependabot PRs re-run green.
- **N17 — Post the #775 review.** Findings in [REVIEW_775.md](REVIEW_775.md): the sandbox blocks `sudo`/apt (so installs can't work when firejail or bubblewrap is present) and bubblewrap silently discards file writes. Recommendation: post it as a comment review on #775 so the agent working that PR fixes items 1–2 before you merge it. Posting public PR comments is outside this run's limits.
- **N18 — Keep or revert the #778 merge into #776's branch** (`f48caff`). It was merged without a human review (D16). Recommendation: keep — it's a security fix plus CI coverage, and you review the whole of #776 in N16 anyway. To revert instead: on #776, **Commits** → `f48caff` → revert.
- **N19 — Offline "install docker" (the demo gap):** contributor PR [#763](https://github.com/cxlinux-ai/cx-core/pull/763) already implements it. Recommendation: after #775 merges, ask @KingParmenides to rebase onto #775's execution gate (preview by default, `[y/N]`), then merge. No bounty is attached to #763 — decide whether to offer one.

## New on Day 3 (2026-10-21)
- **N22 (top) — Review and merge [#780](https://github.com/cxlinux-ai/cx-core/pull/780).** Makes AI answers usable (they printed raw JSON and `-d` never ran them) and adds the 30-second demo recorded from the real local model (`demo/cx-30s.gif`). Recommendation: approve → **Squash and merge**, then have #775 rebase onto it (REVIEW_775 item 5).
- **N23 — Stub commands behind the offline patterns.** `cx new`, `cx save`, `cx restore`, `cx snapshots` print "not yet implemented". *Updated Day 4:* contributor PR [#765](https://github.com/cxlinux-ai/cx-core/pull/765) already implements `cx new` templates; this track reviews its diff on Day 5. Recommendation: no new bounty issue until #765 is assessed; remove the snapshot patterns until snapshots exist.
- **N24 — Demo latency.** 45–62 s per local answer on a 2-vCPU VM. Recommendation: run `demo/record-30s.sh` once on your Mac or a stronger box before using the GIF with investors, so the on-screen `time` reflects realistic hardware.
- **N25 — Review and merge [cx-web #62](https://github.com/cxlinux-ai/cx-web/pull/62) into #60, then #60.** install.sh stops installing an unrelated npm package, fails before changing anything on unsupported systems, and registers `cx`. Recommendation: approve both.
- **N26 — Publish a new APT package from main.** The published 0.3.2 (Feb 23) lacks `cx`, the EOF fix (#772) and #780; its postinst also makes CX the default `x-terminal-emulator`. Recommendation: after N22, cut a release; decide whether the package should take over `x-terminal-emulator`.

## New on Day 4 (2026-10-22)
- **N27 — Review and merge [#781](https://github.com/cxlinux-ai/cx-core/pull/781) (P8 package guard) after #780.** Package changes are previewed with `apt-get -s`, need `[y/N]` (EOF = No), run without a shell and are recorded with an undo. Real install/undo verified on Ubuntu 24.04. It is stacked on #780: merge #780 first, and #781 retargets to `main`. Recommendation: approve → **Squash and merge**.
- **N28 — Tell contributors the bar (public comment, yours to post).** Draft for #763 and #764: "Thanks — before merge, please rebase on main and route package commands through `package_guard::guard` (or return them via `cx ask` execution) instead of running them with `sh -c`. That gives an `apt-get -s` preview, a default-No confirmation and an undo record. See `wezterm/src/cli/package_guard.rs`."

## New on Day 5 (2026-10-23)
- **N29 — docs.cxlinux.com is down.** DNS points at `cxlinux-ai.github.io`, but no GitHub Pages site claims the domain: HTTP returns 404 and HTTPS shows a certificate error. It is linked from the account page (fixed: [cx-web #63](https://github.com/cxlinux-ai/cx-web/pull/63)), the live install.sh (fixed: [cx-web #62](https://github.com/cxlinux-ai/cx-web/pull/62)), cx-core font error messages and the cx-distro installer. Recommendation: remove the `docs` DNS record now (Cloudflare → DNS → `docs` CNAME → Delete). Publish docs later, when they describe the current product (N32).
- **N30 — Legacy brand in public issue text.** 34 of 40 open cx-distro issues (epics #1–#9 and every bounty issue) and cx-core #424, #425, #428 say "Cortex". Recommendation: on the Mac, run `gh issue list --repo cxlinux-ai/cx-distro --state open --limit 100 --json number --jq '.[].number'`. For each issue, edit the body to replace "Cortex" with "CX". Do it in the same pass as N2 (adding the bonus note), since that edits the same 19 issue bodies. Approve and the next run prepares the exact per-issue text.
- **N31 — Rename the SonarCloud project before changing `sonar-project.properties`.** In SonarCloud: Organization `cortexlinux` → Administration → Organization key → `cxlinux-ai`. Project `cortexlinux_cortex` → Administration → Update Key → `cxlinux-ai_cx-core`. Then this track opens the one-line PR. Recommendation: approve. Only the identifiers change; analysis history is preserved.
- **N32 — Retired-CLI documentation.** cx-web `docs/` (Docusaurus, 526 legacy-name hits) and cx-docs (MkDocs, 242) describe the retired Python `cortex` CLI. Recommendation: delete cx-web `docs/` in a PR (it is not deployed). Rewrite a short docs set from the Rust CLI's real `--help` output (ask, install, what, fix, explain, ai download, plus the safety model) as a bounty issue in the $75–100 tier.
- **N33 — Two contributor questions unanswered.** cx-distro #76 (@silasbrookshaha, how to claim $25, 12 days). cx-distro #34 (@mimienco, 2026-09-13, availability and PayPal; another contributor's #83 then completed it). Recommendation: answer both with the payment method (tip.cc on Discord), pay #76 and #83 (N1), and thank @mimienco with a pointer to an open $25 issue.
- **N34 — Close [cx-distro #60](https://github.com/cxlinux-ai/cx-distro/pull/60)** (February clone-URL fix). It is superseded by [#84](https://github.com/cxlinux-ai/cx-distro/pull/84).
- **N35 — Review/merge the Day 5 PRs:** [cx-core #782](https://github.com/cxlinux-ai/cx-core/pull/782) (README accuracy), [cx-distro #84](https://github.com/cxlinux-ai/cx-distro/pull/84) (installer links), [cx-web #63](https://github.com/cxlinux-ai/cx-web/pull/63) (account docs link). All text-only.
