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
| **Real-diff review of 11 open contributor PRs** | [PR_REVIEWS.md](PR_REVIEWS.md): every verdict cites the diff; claims re-verified against the diffs before shipping (3 initial claims corrected) |
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
