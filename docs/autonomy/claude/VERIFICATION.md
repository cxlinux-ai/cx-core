# Independent Verification — 2026-10-25

**Method:** a separate agent with no access to this track's working context re-checked the week from primary evidence:
- a fresh clone and build of cx-core;
- tests on main and on the heads of PR #771, #780 and #781;
- live GitHub REST data;
- curl against the live endpoints;
- runs of the #780 binary against the real local model.

It changed nothing on GitHub. Raw logs were kept in the session workspace (`/home/claude/verify`).

**Result:** 136 checks — 99 verified, 15 false, 12 overstated or stale, 17 could not be verified (some checks carry two verdicts).

## Builds and tests
| Tree | Result |
|---|---|
| main `7b88a92` | `cargo build -p cx-terminal` OK (8 m 41 s); `cargo test` **18 passed** (empty model cache) |
| #771 head | **15 passed** (its PR body said 18 — wrong; the 3 extra came from #772) |
| #780 head | **29 passed**; with the real model, two runs are byte-identical and `echo y \| cx ask -d 'show memory usage'` runs `free -h` |
| #781 head | **44 passed, 1 ignored** (the real-apt test, which needs root) |
| cx-web main | vitest 19/19, tsc clean; #60 and #62 vitest 10/10; #62 install.sh `bash -n` + shellcheck clean; production routing 18/18 |

## False or overstated, and what was done
| # | Claim (where) | Correct value | Fixed |
|---|---|---|---|
| 1 | #771 body "18 passed" | 15 on its own head | Recorded here (merged PR body left as-is) |
| 2 | #779 body "docs/autonomy/claude/ only", "D12–D16, N16–N19" | Also touches BOUNTY_AUDIT.md and PR_REVIEWS.md; now holds D1–D23 and the Day 3–7 logs | Recorded here |
| 3 | #782 README Safety: nothing runs without `-d` | On main, built-in CX actions (e.g. "save my work" → `cx save`) are offered with `Run this? [Y/n]`, Enter = yes, without `-d` | **Fixed** in #782 `7c2cc53` |
| 4–5 | BOUNTY_AUDIT: #45 assigned "since 2026-01-20", #50 "since 2026-01-21" | 2025-12-04 and 2026-01-03 | **Fixed** |
| 6 | BOUNTY_AUDIT: "three outside contributors … against two of them" | Two contributors with open PRs on two issues (closed PRs from a deleted account also targeted #23, #50) | **Fixed** |
| 7 | BOUNTY_AUDIT: open bounties with note "$325+" | $463 | **Fixed** |
| 8–9 | Ledger and PR_REVIEWS: 4 FCFS conflicts; #763/#764 "linked issue: none" | 5th conflict: cx-distro **#25** ($75 + bonus) — cx-core #763 (first, 05-11) and #764 (05-13) both address it | **Fixed** |
| 10 | PR_REVIEWS: ask #73 to link #35 | Already "Refs #35" | **Fixed** |
| 11 | PR_REVIEWS: only CLA checks fail | #744, #764, #757 also fail `Cleanup artifacts` | **Fixed** |
| 12 | Day 4: #763/#764/#765 "no merge base" | Merge base `bf87c78`, 3 commits behind main (artifact of a shallow clone) | **Fixed** |
| 13 | Day 4: "main scheduled workflows green" | `debian11_continuous` failed on main every day 10-20 → 10-25 (fixed by #776) | Corrected in LOG Day 6 |
| 14 | BOUNTY_AUDIT: #26/#34 "closed … completed anyway" | Reopened 2025-12-20; open when completed | **Fixed** |
| 15 | Day 1: "main is green" on `1bf6ce0`/`b1090ad` | `debian11_continuous` failed on both; SonarCloud failed on `b1090ad`, cancelled on `1bf6ce0` | Corrected in LOG Day 6 |
| — | Minor | #771 also reformats `wezterm-font/src/lib.rs`; #772 includes #771's commits; cx-web #57 body still says draft; 27 tracked *file names* in cx-distro contain the legacy name (logos, boot video, `.mo` files); pattern templates are 37, not 35 | Recorded |

## Could not verify (access or scope)
Legacy-org existence and repo redirects (proxy 403); the #778 CodeQL rule id; #781's real-apt test and #62's container installs (both need root/Docker; run by this track on 10-21/10-22); #59's 188-test Playwright suite; the live Stripe checkout (deliberately not exercised); the model-download time; P5 latencies (verifier measured 7–8 ms, against this track's ~54 ms on a debug build under load); cx-docs counts (private); payments made outside GitHub.
