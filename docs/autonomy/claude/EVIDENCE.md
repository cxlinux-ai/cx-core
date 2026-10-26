# CX Linux — Capital-Efficiency Evidence Pack (P10)

**Built:** 2026-10-25 · **Source:** GitHub REST API (`gh api repos/cxlinux-ai/{repo}/…`) and `git` on the default branches of `cx-core`, `cx-web` and `cx-distro`, read on 2026-10-24/25. Every number below can be reproduced with the commands in the appendix. Nothing here comes from memory, decks or conversation.

**What this pack can and cannot show.** GitHub shows *output*: repositories, commits, pull requests, contributors, bounty issues and code size. It does not show headcount, payroll, hours or dollars spent. The investor claim — that this work would traditionally take 3–5 developers about 18 months — needs a cost figure from outside GitHub. This pack supplies the output side, with its limits stated.

## 1. Timeline

| Repo | Created | First commit on default branch | Last commit | Commits on default branch |
|---|---|---|---|---|
| cx-core (Rust terminal + `cx` CLI) | 2025-11-08 | 2025-11-11 | 2026-10-19 | 190 |
| cx-web (cxlinux.com) | 2026-01-25 | 2025-11-29 (history imported) | 2026-10-25 | 1,068 |
| cx-distro (ISO builder, bounty repo) | 2026-01-06 | 2026-01-09 | 2026-10-16 | 70 |

**Activity is concentrated in about 12 weeks (Dec 2025 – Feb 2026).**

| Repo | Commits Dec–Feb | Share of commits | Merged PRs Nov–Feb | Share of merged PRs |
|---|---|---|---|---|
| cx-core | 179 of 190 | 94% | 175 of 182 | 96% |
| cx-web | 983 of 1,068 | 92% | — | — |

Merged PRs by month:

| Repo | Merged PRs by month |
|---|---|
| cx-core | Nov 18 · Dec 50 · Jan 93 · Feb 14 · Mar 3 · Oct 4 |
| cx-web | Feb 39 · Mar 12 · Jul 1 · Oct 6 |
| cx-distro | Jan 2 · Feb 3 · Oct 2 |

## 2. Output

| Measure | cx-core | cx-web | cx-distro | Total |
|---|---|---|---|---|
| Pull requests opened | 374 | 63 | 27 | **464** |
| Pull requests merged | 182 | 58 | 7 | **247** |
| Distinct PR authors other than the owner account and bots | 53 | 2 | 12 | — |
| …of whom had at least one PR merged | 37 | 2 | 5 | — |
| Merged PRs authored by people other than the owner account | 125 | 52 | 5 | **182** |
| GitHub stars / forks | 80 / 68 | 0 / 0 | 15 / 19 | — |

Most-merged outside contributors in cx-core: @Anshgrover23 (23 merged PRs), @Sahilbhatane (16), @0xBigotry7 (9), @sujay-d07 (8), @ShreeJejurikar (6).

**Code written for CX** (line counts with `wc -l`, including comments and tests; default branches as of 2026-10-23):

| Area | Lines |
|---|---|
| cx-core CX-specific modules — GUI AI panel, agents, command blocks, input, subscription, voice, learning, workflows, daemon client, `cx` CLI commands, shell integration, `cx-daemon` | **31,622** |
| cx-core whole Rust tree, mostly the WezTerm terminal it is built on (MIT) | 444,844 |
| cx-web application code (`client/src`, `functions`, `shared`, `server`; TS/TSX) | 20,704 |
| cx-distro build and tooling scripts (sh/py) | 6,488 |

The CX share of cx-core is about 7% of its Rust lines. The product builds on a mature open-source terminal and adds an AI/CLI layer rather than writing a terminal from scratch. That reuse is itself a capital-efficiency fact, and should be presented as one.

## 3. Contributor economics (bounties)

| Measure | Value | Source |
|---|---|---|
| Bounty-labeled issues in cx-core, all time | 150 | `issues?labels=bounty&state=all` |
| …closed as completed | 47 issues, **$3,263** in stated bounties | amounts parsed from issue bodies |
| …closed as not planned | 100 issues, $3,125 stated | — |
| …open | 2 issues, $300 (#425, #428) | — |
| Owed now on merged cx-distro PRs #76, #83 | $50, no payment acknowledgement on GitHub | [BOUNTY_AUDIT.md](../BOUNTY_AUDIT.md) |

What GitHub cannot show: whether the $3,263 was paid, and when. Payments run through tip.cc on Discord. Treat $3,263 as the stated value of completed bounty work, not as cash spent, until it is reconciled against payment records.

## 4. AI-assisted delivery — what the record shows

- **cx-core:** 53 of 190 commits carry an explicit AI attribution — a Claude/Copilot/Cursor co-author trailer, a "Generated with Claude" footer, or an AI bot author.
- **cx-web:** 16 of 1,068 commits.
- **cx-distro:** 5 of 70 commits.

This is a **lower bound**. Tools such as Cursor and Replit commit under the user's own name without a trailer, and the top cx-web committer accounts (`MichaelMorgan18`, `h15629526027`) carry no tool attribution. GitHub data therefore can't prove the claimed AI-augmented delivery model. Stating "at least 28% (53 of 190) of cx-core commits are explicitly AI-attributed" is supportable; a higher figure needs tool-side records (Cursor or Replit usage exports).

## 5. Quality signals from this week (verified, not yet merged)

| Signal | Evidence |
|---|---|
| Public build restored (red since 2026-03-15) | #771, merged 2026-10-19 |
| EOF-as-consent safety bug fixed | #772, merged 2026-10-19 |
| Real local-model answer path fixed + 30-s demo recorded from the real model | #780, CI green except a Debian 11 job fixed by #776 |
| Package changes previewed with `apt-get -s`, confirmed, recorded with undo; real install/undo verified on Ubuntu 24.04 | #781 |
| cxlinux.com QA 115/188 → 190/190; SEO audit 8/8 on production | cx-web #57–#59, #61 (merged, live) |

## 6. How to use this in the raise

- **Supported now:**
  - "247 merged PRs (219 of them between November 2025 and February 2026) and 31.6k lines of CX-specific Rust/shell across three repos."
  - "53 outside contributors opened PRs to the core repo; 37 had work merged."
  - "$3,263 of bounty-priced work closed as completed."
- **Needs a number from outside GitHub:** total spend (bounties actually paid plus any contractor and tool costs) to set against "3–5 developers × 18 months". With that figure, the comparison becomes cost per merged PR, or spend against a team-month estimate. Without it, keep the claim qualitative.
- **Avoid:** describing modules as shipped features when they are not wired into the running product. Examples are the GUI Tab completion (`input/`, 2,683 lines) and the `cx new/save/snapshots` stubs. A technical investor who builds from source will check.

## Appendix — reproduce

```bash
gh api repos/cxlinux-ai/cx-core --jq '.created_at,.stargazers_count,.forks_count'
for p in 1 2 3 4; do gh api "repos/cxlinux-ai/cx-core/pulls?state=all&per_page=100&page=$p" --jq '.[] | [.number,.user.login,(.merged_at//"")] | @tsv'; done
for p in 1 2; do gh api "repos/cxlinux-ai/cx-core/commits?per_page=100&page=$p" --jq '.[] | [.commit.author.date[0:10], (.author.login // .commit.author.name)] | @tsv'; done
for p in 1 2; do gh api "repos/cxlinux-ai/cx-core/issues?state=all&labels=bounty&per_page=100&page=$p" --jq '.[] | select(.pull_request|not) | [.number,.state,.state_reason] | @tsv'; done
{ git ls-files wezterm-gui/src/ai wezterm-gui/src/agents wezterm-gui/src/blocks wezterm-gui/src/input wezterm-gui/src/subscription wezterm-gui/src/voice wezterm-gui/src/learning wezterm-gui/src/workflows wezterm-gui/src/cx_daemon shell-integration cx-daemon; git ls-files wezterm/src/cli | grep -E 'ask|/ai\.rs|daemon|license|new\.rs|snapshot|shortcuts|security|model_utils'; } | xargs cat | wc -l
```
Exclusions used for "outside" counts: the owner account `mikejmorgan-ai`, logins ending in `[bot]`, and `Copilot`.
