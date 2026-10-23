# CX Linux — Autonomous Week Plan

**Window:** Mon 2026-10-19 → Mon 2026-10-26 (America/Denver)
**Owner:** Claude (autonomous), reviewer: Mike Morgan
**Mission:** Move CX Linux to the project Definition of Done — canonical repo confirmed, MVP demo assets verified, bounty system correct end-to-end, contributor fairness verifiable from GitHub data, PR review done from real diffs — so seed-round material rests on proven ground.

Ranked by impact × dependency. Each item names its proof of done.

## Ground truth established Day 1 (2026-10-19)

| Fact | Evidence |
|---|---|
| Canonical org is `cxlinux-ai`; the legacy org no longer exists | `gh repo list` on the legacy handle returns "not recognized as a GitHub user or organization" |
| Product repo is `cxlinux-ai/cx-core` (Rust, WezTerm-based terminal + `cx` CLI) | `gh repo view cxlinux-ai/cx` → `cxlinux-ai/cx-core`; legacy names redirect to it |
| Most contributor-active repo is `cxlinux-ai/cx-distro` | merges on 2026-10-10 (#76) and 2026-10-16 (#83) |
| One-liner install is live at `https://cxlinux.com/install.sh` | HTTP 200, `application/x-sh`, 8,249 bytes |
| APT repo is live at `https://repo.cxlinux.com` | `key.gpg` 200 (3,898 B), `apt/dists/stable/Release` 200 |
| `cxlinux.ai` redirects to `cxlinux.com`; the legacy apt host resets connections | curl probes 2026-10-19 |
| Public `cx-core` cannot be built from a clean checkout | private git dependency `mikejmorgan-ai/hrm-ai-standalone` → HTTP 401 during dependency resolution |
| `CX Terminal Build` workflow has failed on `main` since 2026-03-15 | `gh run list --workflow cx-build.yml` |

## Ranked plan

| # | Item | Why it matters | Proof of done | Day |
|---|---|---|---|---|
| P0 | **Stop non-interactive auto-execution** — EOF on `Run this? [Y/n]` executed the command | Safety-first is a stated differentiator | `cx ask … </dev/null` refuses; unit tests; CI green | 1 |
| P1 | **Restore public buildability of cx-core** — remove the private git dependency from the public manifest | Contributors, CI, and any investor doing "clone → build" currently fail at step one | Clean `cargo build -p cx-terminal` + `cargo test -p cx-terminal` in a fresh environment; CI green on the PR | 1 |
| P2 | **Bounty ledger + compliance audit** across cx-core and cx-distro | Contributor trust is part of the asset; two pay-on-merge bounties are outstanding | `docs/autonomy/BOUNTY_AUDIT.md` with every open bounty issue, amount, bonus-note status, and owed payouts | 1 |
| P3 | **Real-diff review of every open contributor PR** | FR-005; several PRs collide with assigned issues (FCFS) or bypass dry-run safety | `docs/autonomy/PR_REVIEWS.md` with per-PR verdict and line-level findings | 1–2 |
| P4 | **Fix `CX Terminal Build` on main** (root cause, not suppression) | Red main undermines every PR's signal | Workflow green on main | 2 |
| | ↳ *Update 2026-10-19 09:40 MT:* the P1 branch (#771) turns `CX Terminal Build` green — Build (macos-14), Build (ubuntu-22.04), Cargo Check, Test Suite all pass — so P1 was the root cause. Remaining: the `debian11` packaging job 404s on `debian-security` (stale package index in that container). | | | |
| | ↳ *Update 2026-10-20:* P4 closed by #776 + #778 (all three Debian 11 workflows on archive sources; job passes on #776). Awaiting review/merge. | | | |
| P5 | **Verify the "Tab moment"** — instant fuzzy suggestions without an LLM round-trip | Single most important demo beat | Reproducible terminal recording + measured latency of the suggestion path | 2–3 |
| | ↳ *Finding 2026-10-20 (P5):* there is no Tab-moment feature in the running product. GUI Tab completion (`wezterm-gui/src/input/`, `ModernInput`) compiles but is never instantiated; Tab goes to the user's shell. The live instant path is the `cx ask` pattern matcher: ~54 ms median, no LLM wait (debug build). See LOG Day 2. | | | |
| P5b | **Offline answer for common install intents** — today `cx ask "how do I install docker"` with no API key or local model returns "No AI backend"; CX-native intents (new/save/snapshots) already work offline | PLAN.md's own success criterion and the offline-capable claim (spec §8) | Offline `cx ask` returns a vetted command for the top install intents (build on #763's matcher), behind the D8 confirmation rules | 3–4 |
| P6 | **Verify one-liner install end-to-end** on Ubuntu 24.04 (container) | AC-002 | Script run log: install completes, `cx status` and `cx ask` run | 2–3 |
| P7 | **Demo GIF asset** — confirm what exists; script a reproducible 30-second recording (asciinema/vhs tape) | AC-002, investor demo | Committed tape file + rendered GIF | 3–4 |
| | ↳ *2026-10-20:* P5b is the subject of contributor PR #763 — not duplicated (D13). | | | |
| P8 | **Dry-run/sandbox-by-default guard for package execution paths** | Spec §8/§10 safety differentiator; open PRs execute `sudo apt install` directly | Shared helper in `cx` that defaults to preview; tests prove no execution without explicit confirm | 4–5 |
| P9 | **Brand hygiene sweep** across org repos (legacy name in configs, identifiers, docs) | AC-001 | Grep report = zero non-vendored hits outside explicitly-legacy notes | 5 |
| P10 | **Capital-efficiency evidence pack** from real repo data (commits, contributors, merged PRs, cost) | FR-007 seed support | `docs/autonomy/EVIDENCE.md` sourced only from GitHub data | 6 |
| P11 | **Week-end report** | Mike opens the repo and sees verified progress | LOG final entry, NEEDS_MIKE short and ready-to-approve | 7 |

## Operating rules for this week

- Merges that create money obligations (any contributor bounty PR) are queued in NEEDS_MIKE, never merged autonomously.
- Docs-only merges are safe: build/package workflows ignore `docs/**` and `*.md`.
- Merges touching `**/*.rs`, `Cargo.toml`, or `Cargo.lock` trigger the `*_continuous` package workflows; they ship only after CI is green and are logged with a revert path.
- No comments, reviews, or issue edits are posted publicly on contributor threads — those are communications as the company and are drafted in NEEDS_MIKE instead.
- No tags/releases (`v*` tags trigger `cx-release.yml`).

### P8 status (2026-10-20)
Covered by the parallel run's [#775](https://github.com/cxlinux-ai/cx-core/pull/775). Reviewed from the diff with sandbox tests: gate logic correct; sandbox blocks `sudo`/apt and bubblewrap discards writes. See [REVIEW_775.md](REVIEW_775.md). Not duplicated (D12).
*Update 2026-10-22:* the package-specific part is now built in [#781](https://github.com/cxlinux-ai/cx-core/pull/781) (D20); #775 keeps the general gate, sandbox and audit/undo.

### P6/P7 status (2026-10-21)
- P6 done: install.sh verified in Ubuntu 24.04/22.04 and Debian 12 containers; fixes in cx-web #62.
- P7 done: real-model 30-second demo in cx-core #780 (`demo/`). Recording also exposed and fixed the unusable AI answer path.

### Re-rank (Day 4, 2026-10-22) — from evidence
| Rank | Item | Status / evidence | Owner |
|---|---|---|---|
| 1 | Merge order to make the demo path real on main: #776 (CI) → #780 (AI answers + demo) → #781 (P8 guard) → #775 rebased (sandbox/audit, items 1, 2, 5) | #780 green except `debian11`, which #776 fixes | Mike (N16, N22, N27) |
| 2 | **P8** shared package guard | Built: [#781](https://github.com/cxlinux-ai/cx-core/pull/781) — `apt-get -s` preview, `[y/N]`, record + undo; real install/undo verified in Ubuntu 24.04 (D20) | done, review |
| 3 | Contributor bar: #763 (offline install intents) and #764 (package parsing) route through `package_guard::guard` | Both build `sudo apt install …` text; no merge base with current main (branched before #771) | contributors, after #781 |
| 4 | New APT release from main | Published 0.3.2 lacks `cx`, #772, #780, #781 | Mike (N26) |
| 5 | Stub commands (`cx new/save/restore/snapshots`) | Contributor PR #765 implements `cx new` templates (May, unreviewed) — review it before writing a bounty issue (N23 updated) | Day 5 review |
| 6 | P9 brand sweep | Day 5 | this track |
| 7 | P10 evidence pack | Day 6 | this track |
| — | P5 GUI Tab moment | Not wired in product (Day 2). Not a week-scale fix; recorded for the roadmap | — |
