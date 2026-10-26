# Open Contributor PR Reviews (from actual diffs)

**Run:** 2026-10-19 · **Method:** `gh pr diff` for every open contributor PR, read line by line; automated-tool status (CodeRabbit/SonarCloud) recorded but not relied on (FR-005).
**Nothing below has been posted to GitHub.** Ready-to-post review text for each PR is in NEEDS_MIKE.md (item N3).

Safety bar applied (spec §8/§10): package-changing operations default to preview/dry-run and execute only on explicit confirmation.

## Refresh — 2026-10-23

Every PR below was re-checked against live GitHub. **No contributor PR received a new commit since the 2026-10-19 reviews**, so the verdicts stand except where noted.

- **#765 (`cx new` templates) — verdict changed: Approve after two changes.** The Day 1 note that "`cx new` is already implemented on main" was wrong: main's `new.rs` prints "not yet implemented". Tested empirically: #765's `new.rs` was applied to current main. `cargo test -p cx-terminal` passed 24/24, including 6 tests from the PR. Then each template was generated through a local, uncommitted top-level `new` dispatch:
  - rust, go, node and python projects run and print "Hello from demo-…"; python creates a real `.venv`;
  - fastapi, react, nextjs and docker write their files;
  - `../evil` is rejected as a path, a non-empty target dir is refused, and an unknown template errors.

  Changes needed:
  1. `cx ask` patterns send users to `express` and `db` templates, which #765 lacks.
  2. `new` is reachable only as `cx-terminal cli new`, which first connects to the mux server and fails without one. On a fresh install, `cli new` exits 1 before running (pre-existing on main). Register `new` as a top-level subcommand, the way #774 does for `activate`/`license`.

  Issue #708 carries no bounty; price it or label it `no-bounty` before merge (N8).
- **#763 / #764 (NL install):** verdicts stand. The safety bar is now concrete: route package commands through `package_guard::guard` from [#781](https://github.com/cxlinux-ai/cx-core/pull/781). Both also need a rebase; they branched before #771 and share no merge base with current main. Draft request: NEEDS_MIKE N28.
- **Corrections (2026-10-25, independent verification):**
  - #763 and #764 both link **cx-distro #25** ($75 + bonus), not "none"; #763 was first (FCFS).
  - #73 already says "Refs #35".
  - Besides CLA, #744, #764 and #757 also fail `Cleanup artifacts`.
  - #763/#764/#765 *do* share merge base `bf87c78` with main (3 commits behind); the Day 4 "no merge base" note came from a shallow clone.
- **cx-distro #60** (Mike's clone-URL fix, February) is superseded by [#84](https://github.com/cxlinux-ai/cx-distro/pull/84), which removes every remaining legacy-org link. Recommend closing #60.

## cx-core

All cx-core PRs show 2 failing checks: both are `CLA Verification` / `cla-check` (contributor CLA not signed) — not code failures.

| PR | Author | Size | Linked issue | Verdict | Findings from the diff |
|---|---|---|---|---|---|
| [#744](https://github.com/cxlinux-ai/cx-core/pull/744) shell integration for `cx fix` | @rronit786 | +164 / 3 files | #712 (no bounty) | **Changes requested** | (1) `exec 2> >(tee "$HOME/.cx/stderr.tmp" >&2)` routes every interactive shell's stderr through a pipe for the life of the session — programs that check `isatty(2)` lose color/progress output, and interactive tools that draw on stderr misbehave. (2) The prompt hook truncates `stderr.tmp` with `: >` while `tee` keeps the file open at its old offset without `-a`, so subsequent writes land past EOF and produce sparse files with stale gaps. (3) Captured stderr can contain secrets (tokens echoed by CLIs) and is persisted to `~/.cx/last_error` with default permissions. (4) Appends to `.bashrc`/`.zshrc` with no uninstall path. Recommend: capture only on demand (`cx fix` re-runs the last command) or use per-command `preexec` capture with `tee -a`, `chmod 600`, and a `cx setup shell --remove`. |
| [#763](https://github.com/cxlinux-ai/cx-core/pull/763) NL install intent | @KingParmenides | +563 / 3 files | none | **Changes requested** | Well-structured offline intent matcher with a confidence threshold (0.68) and a clarification path — good fit for the "Tab moment" offline goal. But `handle_install_intent` runs `sudo apt install` directly after a y/N prompt and `-y` skips even that; no dry-run (`apt-get -s`) preview, no transaction record, no undo. Includes 6 inline unit tests for intent matching (none cover the execution path). Overlaps #764. |
| [#764](https://github.com/cxlinux-ai/cx-core/pull/764) NL package install parsing | @wangxq-cc | +317 / 2 files | none | **Changes requested** | Implements the same feature in `wezterm-gui/src/agents/package.rs`; builds `sudo apt install -y {packages}` (hard-coded `-y`). Includes 9 inline unit tests for parsing. Must be reconciled with #763 — pick one implementation (recommend #763's structure plus a dry-run default). |
| [#765](https://github.com/cxlinux-ai/cx-core/pull/765) `cx new` scaffolding | @Da7-Tech | +956 / 1 file | #708 (no bounty) | **Needs product decision** | Rewrites `wezterm/src/cli/new.rs`. `cx new` is already implemented on main (PLAN.md marks it done 2026-01-26); this PR is a large replacement, not a gap fill (6 inline unit tests included). Decide whether #708 is still open work before reviewing further. |
| [#753](https://github.com/cxlinux-ai/cx-core/pull/753) dependency conflict predictor | @lustsazeus-lab | +786 / 5 files | #428 ($150, assigned @Suyashd999) | **Hold — FCFS conflict** | Python module under `cx/` in a Rust codebase; nothing in the `cx` binary calls it, so it does not ship to users as written. Includes a test file and dry-run handling. Cannot be accepted for the bounty while #428 is assigned to someone else. |
| [#766](https://github.com/cxlinux-ai/cx-core/pull/766) native llama.cpp inference | @Ishant5436 | **+551,469 / 598 files** | #425 ($150, assigned @sujay-d07) | **Hold — do not merge as-is** | Vendors the llama.cpp source tree into the repo (GitHub cannot render the diff: >300 files) and adds a CMake build step to `wezterm-gui/build.rs`, changing build requirements for every contributor. Uses legacy-brand identifiers in module and branch names (AC-001). FCFS conflict with the assignee. Main **already** links llama.cpp through the `llama-cpp-2` crate (workspace `Cargo.toml` line 133, used by `wezterm` and `wezterm-gui`), so the vendored copy duplicates an existing dependency. The useful part of this PR — replacing the Ollama process path with in-process inference — should be rebuilt on the existing `llama-cpp-2` binding. |
| [#757](https://github.com/cxlinux-ai/cx-core/pull/757) generic font suggestions | @brainRottedCoder | +110 | #728 (closed) | **Rebase needed** | Merge conflicts with main; the issue it targets was closed by #759. Likely superseded. |
| Dependabot #747, #748, #749, #761, #762 | bot | small | — | **Re-run after P1** | Test/Build workflows fail at ~1 minute (dependency-resolution stage). Run logs have expired, so the cause is unconfirmed; the private git dependency reproduces exactly this failure in a clean environment. Re-run after the P1 fix lands to confirm. |

## cx-distro

| PR | Author | Size | Linked issue | Verdict | Findings from the diff |
|---|---|---|---|---|---|
| [#71](https://github.com/cxlinux-ai/cx-distro/pull/71) Safe NVIDIA installer with rollback | @businesscurry123 | +1,070 / 6 files | #24 ($100, unassigned) | **Strongest candidate — approve after one fix** | `set -euo pipefail`, 19 dry-run references, snapshot of DKMS/package state before change, rollback path, test script added, mergeable, CI green. Install path simulates first (`apt-get -s install "$target"`) before any change — correct. One fix before merge: in the rollback path, packages absent from the snapshot are purged (`apt-get purge -y`) *before* the snapshot's packages are re-installed; if that restore install fails, the machine is left with no driver. Simulate the restore set (`apt-get -s install …restore_specs`) before purging, and abort rollback if simulation fails. Clean FCFS. |
| [#75](https://github.com/cxlinux-ai/cx-distro/pull/75) dependency conflict resolver | @jienigoto | +414 / 3 files | #50 (assigned @Sahilbhatane) | **Hold — FCFS + conflicts** | Merge conflicts; contains one `rm -rf` in test scaffolding (scoped to a temp dir — acceptable). Same problem space as #72. |
| [#72](https://github.com/cxlinux-ai/cx-distro/pull/72) package conflict resolver | @dnesdan | +525 / 5 files | #45 (assigned @Sahilbhatane) | **Hold — FCFS + conflicts** | Merge conflicts; overlaps #75. Choose one resolver design for both issues. |
| [#73](https://github.com/cxlinux-ai/cx-distro/pull/73) package changelog viewer | @patrykcodex-del | +386 / 4 files | none in PR (matches #35, $25) | **Rebase needed** | Read-only feature, tests added, low risk. Conflicts with main. Ask author to link #35. |
| [#62](https://github.com/cxlinux-ai/cx-distro/pull/62), [#61](https://github.com/cxlinux-ai/cx-distro/pull/61), [#60](https://github.com/cxlinux-ai/cx-distro/pull/60) | @mikejmorgan-ai | small | — | **Stale own PRs** | Domain/SPDX/clone-URL fixes from February; some already superseded by later commits on main. Close or rebase. |
