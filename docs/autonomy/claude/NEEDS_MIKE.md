# Needs Mike — ready to approve (trimmed 2026-10-25)

Reply with the number and "approved" (or a change), and the next run does exactly what is written. Everything here is outside the autonomy limits: merges need your review, money, public posts, or account access. Full history is in git (`git log -p docs/autonomy/claude/NEEDS_MIKE.md`).

| # | Approve | What it does | Cost |
|---|---|---|---|
| **1** | **Merge chain (in order):** [#776](https://github.com/cxlinux-ai/cx-core/pull/776) CI unblock (includes the #778 CLA security fix, `f48caff`; keep it) → [#780](https://github.com/cxlinux-ai/cx-core/pull/780) AI answers + real-model demo → [#781](https://github.com/cxlinux-ai/cx-core/pull/781) package guard. Then #775 rebases on them | The core product path works on `main`: AI answers render and run after `[y/N]`, and package changes are previewed, confirmed and recorded. Unblocks CI for every open PR. Independently re-verified 2026-10-25: 29 tests pass on #780, 44 on #781 | none |
| **2** | **Merge text-only fixes:** [cx-core #782](https://github.com/cxlinux-ai/cx-core/pull/782) README; [cx-distro #84](https://github.com/cxlinux-ai/cx-distro/pull/84) installer links; [cx-web #62](https://github.com/cxlinux-ai/cx-web/pull/62) into #60, then [#60](https://github.com/cxlinux-ai/cx-web/pull/60) | README tells the truth; installer links work. install.sh stops installing an unrelated npm package and fails safely on unsupported systems | none |
| **3** | **Pay $50 and answer contributors:** cx-distro #76 (@silasbrookshaha, waiting since Oct 11) and #83 (@Ravikirar), $25 each via tip.cc; reply on #76 and #83 (Appendix A); answer @mimienco on #34 | Clears the money owed and two unanswered contributor questions | **$50** |
| **4** | **Delete the `docs` DNS record** (Cloudflare → cxlinux.com → DNS → `docs` CNAME → Delete) | docs.cxlinux.com currently shows a certificate error / 404 | none |
| **5** | **Let the next run post reviews as comments** (no approve/merge): [#775](https://github.com/cxlinux-ai/cx-core/pull/775) review (REVIEW_775.md); #763/#764 — rebase and route package commands through `package_guard` (cx-distro #25 FCFS: #763 first); [#765](https://github.com/cxlinux-ai/cx-core/pull/765) — register `new` top-level and add `express`/`db` templates; the 11 PR_REVIEWS verdicts | Contributors get actionable, diff-based feedback | none |
| **6** | **One pass over bounty issue text:** add the post-funding bonus note to the 19 cx-distro issues missing it (Appendix B) and replace the legacy brand with "CX" in 34 cx-distro issue bodies and cx-core #424/#425/#428 | Bounty template compliance (FR-003) and brand (AC-001) | **+$475** post-funding |
| **7** | **Stale assignments:** post the 7-day check-in (Appendix D) on cx-core #425, #428 and cx-distro #45, #50; unassign if there's no reply by Nov 1 | Fair FCFS for contributors with waiting PRs | none |
| **8** | **Rename SonarCloud:** org `cortexlinux` → `cxlinux-ai`, project key `cortexlinux_cortex` → `cxlinux-ai_cx-core`; then the next run opens the one-line `sonar-project.properties` PR | Removes the last legacy identifier in cx-core config | none |
| **9** | **After 1: cut a new APT release from `main`.** Decide whether the package keeps making itself the default `x-terminal-emulator` (recommend: no) | Users get `cx`, the EOF fix, usable AI answers and the package guard; published 0.3.2 has none of these | none |
| **10** | **Quick yes/no decisions** (recommendation in bold): <br>• drop Debian 11 support next release **yes**<br>• delete cx-web `docs/` (retired-CLI docs, not deployed) and open a $75–100 docs bounty **yes**<br>• label cx-core #708/#712 `no-bounty` **yes**<br>• merge cx-distro #71 after its rollback fix ($100) **yes**<br>• close cx-distro #60 **yes**<br>• approve Dependabot #747/#748/#761 **yes**<br>• resubmit sitemap in Search Console **yes**<br>• homepage title vs H1 **keep**<br>• forward clinux.ai if you own it **yes**<br>• re-record the demo GIF on your Mac before investor use **yes**<br>• paste Appendix E into the project instructions **yes** | Each one is independent | $100 on #71 merge |

## Appendix A — N1 thank-you replies (professional default)

**On cx-distro #76:**
> Thanks @silasbrookshaha — merged and appreciated. Your $25 bounty for #26 has been sent via tip.cc. Sorry for the slow reply on the claim question.

**On cx-distro #83:**
> Thanks @Ravikirar — merged and appreciated. Your $25 bounty for #34 has been sent via tip.cc.

**On cx-distro #34 (to @mimienco):**
> Sorry this went unanswered — #34 was completed by another contributor's PR (#83) before we replied. Bounties are paid via tip.cc on our Discord. Open $25 tasks include #27–#33; comment on one to claim it first-come-first-served.

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

