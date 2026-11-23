# Autonomous Week Log — CX Linux

## Day 1 — Mon 2026-10-19 (cycle 1)

### Shipped (with proof)

| What | Proof |
|---|---|
| **FR-001 resolved from live GitHub state** — canonical org `cxlinux-ai`, product repo `cxlinux-ai/cx-core`; legacy org gone | `gh repo view cxlinux-ai/cx` → `cxlinux-ai/cx-core`; legacy handle "not recognized as either a GitHub user or an organization"; legacy repo names resolve to the same HEAD `bf87c78` |
| **P1 — public build restored** (private `hrm-ai` git dep removed from public manifest) | Before: `cargo build` fails in dependency resolution with HTTP 401 on `mikejmorgan-ai/hrm-ai-standalone` (private). After: `cargo build -p cx-terminal` → `Finished dev profile in 8m 01s` from a clean environment. `Cargo.lock` diff is removal-only (0 added lines; 13 crates removed: `hrm-ai` + 12 it alone pulled in, incl. `rsa`) |
| **P0 — non-interactive auto-execution fixed** | Before: `cx ask "save my work" </dev/null` printed `Run this? [Y/n]` then executed. After: prints "No interactive input; not running." Piped `y` runs, `n` cancels, `-d -y` runs. 3 new unit tests |
| **Test suite** | `cargo test -p cx-terminal`: **18 passed, 0 failed** (15 existing + 3 new) |
| **Install + APT endpoints verified live** | `https://cxlinux.com/install.sh` 200 (`application/x-sh`, 8,249 B); `https://repo.cxlinux.com/key.gpg` 200; `…/apt/dists/stable/Release` 200; `cxlinux.ai` → 301 `cxlinux.com` |
| **Bounty ledger + compliance audit** | [BOUNTY_AUDIT.md](BOUNTY_AUDIT.md): $50 owed on 2 merged PRs; 19 issues missing the bonus note; 4 FCFS conflicts |
| **Real-diff review of 11 open contributor PRs** | [PR_REVIEWS.md](../PR_REVIEWS.md): every verdict cites the diff; claims re-verified against the diffs before shipping (3 initial claims corrected) |
| **Week plan, decisions, blockers, approvals queue** | PLAN / DECISIONS (D1–D9) / BLOCKERS (B1–B2) / NEEDS_MIKE (N1–N8) |
| **Continuation cycles scheduled** | Day 1 cycle 2 (19:25 MT today), Days 2–7 and final report (11:25 MT daily through Mon Oct 26) |

### Findings that change the plan
- The project spec describes the retired Python repo; reality is a Rust/WezTerm codebase (D2, NEEDS_MIKE N7).
- Offline demo gap: `cx ask "how do I install docker"` with no API key/local model → "No AI backend" (PLAN P5b). CX-native intents (`cx new`, `cx save`, `cx snapshots`) already resolve offline.
- `CX Terminal Build` has been red on main since 2026-03-15; logs expired (B2) — re-derive on the next run (P4).
- README "Build from Source" copies `target/release/cx`; the binary target is `cx-terminal` — fix in the P9 sweep.
- Open PR #766 vendors llama.cpp (551k lines) although main already links it via the `llama-cpp-2` crate.

### Next
- Cycle 2 (tonight): confirm CI on the three PRs, merge per D6, re-run Dependabot checks, start P4.
- Day 2: P4 green main, P5 Tab-moment latency verification.

### Risks / blockers
- Pushes depend on the Mac being awake (B1 → N6).
- $50 in owed bounties and an unanswered claim question (N1) are a contributor-trust risk this week.

## Day 1 — Mon 2026-10-19 (cycle 1b, 09:36 MT scheduled follow-up)

### Shipped / verified
| What | Proof |
|---|---|
| **#771 is green on everything that matters** — all 4 required checks (Cargo Check, Rustfmt, Test Suite, Documentation Tests) plus CX Terminal Build on macOS-14 and Ubuntu 22.04, Clippy, Terminal/Termwiz/BiDi tests, CodeQL, Sonar, CLA | `gh pr checks 771`, head `0dc51c0` |
| **P4 root cause confirmed** — the `CX Terminal Build` workflow red on main since 2026-03-15 is fixed by P1 | same run; macOS + Ubuntu build jobs pass |
| **Rustfmt pre-existing failure fixed** — `wezterm-font/src/lib.rs` (2 diffs on main) | commit `0dc51c0`; `cargo fmt --all -- --check` → 0 diffs |
| **#772 restacked** on #771's branch so its CI resolves deps; GitHub retargets it to main when #771 merges | head `4345d75`, base `fix/public-build-private-dep` |

### Not done (and why)
- **#771 not merged:** the `main-branch-protection` ruleset requires 1 approving review; the PR is from Mike's account so it can't self-approve. Not bypassed with `--admin` (D11) → NEEDS_MIKE N0.
- **Dependabot re-runs skipped:** they would fail again until #771 is on main (their branches don't contain the fix); re-run after merge.
- **Remaining failure:** `debian11` packaging job — apt 404s on `debian-security` in the `Install git` step (B4).

### Discovered
- A **parallel Cursor-driven autonomy run** ("Linus", goal: first paying user) is working the same repos and rewrote five files in `docs/autonomy/` on #773 from its own canonical copies. Its plan independently recommends merging #771 → #772 → #774. This track now writes to `docs/autonomy/claude/` so neither overwrites the other (D10). Its commits as `@cursoragent` fail the CLA check (N9).

### Next
- After Mike approves #771: merge, confirm #772 retargets and goes green, merge it; re-run Dependabot; then P4 remainder (debian11 apt index) and P5 Tab-moment verification.

## Day 1 — Mon 2026-10-19 (cycle 2, 19:25 MT)

### Shipped / verified
| What | Proof |
|---|---|
| **#771 and #772 merged by Mike (12:50 MT)** | merge commits `1bf6ce0`, `b1090ad` on main |
| **Main is green** — CX Terminal Build, CX Terminal Tests, CodeQL, Nix, fmt, and 9 packaging pipelines (Ubuntu 22.04/24.04, Debian 12, Fedora 39/40/41, CentOS 9, macOS) pass on both merge commits | `gh run list --branch main` |
| **5 Dependabot PRs brought up to date with main** (#747 #748 #749 #761 #762) so their CI runs against the fix | `gh pr update-branch` ✓ ×5 |
| **Debian 11 root cause found and fix built** — Debian 11 LTS EOL 2026-08-31; security packages moved to archive.debian.org. Fix in generator + 3 workflows; tested under `bash -eo pipefail` for match and no-match | commit `1bc243a` (local, push blocked B5) |

### Corrected
- B4's first hypothesis ("add apt update") was wrong — the workflow already does it. Root cause is the EOL archive move.

### Not done (and why)
- Debian 11 PR not opened: pushing workflow files needs `workflow` scope (B5 → N10).

### Next
- Day 2 (11:25 MT): Dependabot CI results → merge-ready list; P5 Tab-moment latency; P5b offline install intents; push Debian 11 fix if N10 done.
