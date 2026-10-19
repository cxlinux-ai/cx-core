# Needs Mike — ready to approve

Each item is outside the autonomy limits (money, external communication, or account access). Recommendation first; approving means "do exactly this." Reply with the item number + "approved" and the next run executes it.

| # | Item | Recommendation | Cost / commitment | Why it's queued |
|---|---|---|---|---|
| ~~**N0**~~ | ✅ **DONE 12:50 MT** — Mike merged #771 and #772. ~~**Approve [#771](https://github.com/cxlinux-ai/cx-core/pull/771)** — restores the public build; all 4 required checks + CX Terminal Build (macOS, Ubuntu) pass. The repo ruleset needs 1 approving review and the PR comes from your account, so it can't self-approve | Open the link → **Files changed** → **Review changes** → **Approve** → **Squash and merge**. #772 then retargets to main automatically ~~ | — | — |
| **N1** | **Pay two merged bounties** — cx-distro [#76](https://github.com/cxlinux-ai/cx-distro/pull/76) @silasbrookshaha $25 (merged Oct 10, asked how to claim Oct 11, unanswered) and [#83](https://github.com/cxlinux-ai/cx-distro/pull/83) @Ravikirar $25 (merged Oct 16) | Pay both via tip.cc today and post the drafted thank-you (Appendix A) | **$50** | Spending + public reply |
| **N2** | **Add the post-funding bonus note to 19 non-compliant cx-distro bounty issues** (#27–33, #35–45, #48) | Approve; script in Appendix B edits all 19 in one pass | **+$475 post-funding** commitment | Changes financial terms publicly |
| **N3** | **Post the real-diff reviews** on 11 open PRs (findings in [PR_REVIEWS.md](PR_REVIEWS.md)) | Approve; Appendix C posts them as "comment" reviews (not approve/merge) | none | Public communication as the company |
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
- **N10 — Let pushes change CI workflow files (one-time).** The Mac's GitHub login has `repo` but not `workflow` scope, so GitHub refuses any push that edits `.github/workflows/`. The Debian 11 CI fix is committed and waiting (`ci/debian11-archive-security`, patch also saved at `docs/autonomy/claude/patches/p4-debian11.patch`).
  - **Browser (recommended, also clears N6):** open https://github.com/apps/claude/installations/select_target → pick **cxlinux-ai** → **All repositories** → **Install**.
  - The next run pushes the branch and opens the PR.
- **N11 — Keep shipping Debian 11 packages?** Debian 11 reached end of life on 2026-08-31 (no more security updates). README still lists it as supported. Recommendation: keep building it this week via the archive fix (zero user impact), and drop it from the supported-platforms table and CI next release. Approve "drop Debian 11" or "keep".
