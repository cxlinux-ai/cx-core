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

## Day 2 — Tue 2026-10-20 (11:25 MT)

### Overnight (verified against GitHub)
- Mike merged #773 (docs) 2026-10-19 16:09 MT; installed the Claude GitHub App (N10/N6 done).
- The parallel run opened #775 (dry-run by default + sandbox + audit/undo), #776 (CLA allowlist + Debian 11 + docs links), #777 (its docs sync).

### Shipped / verified
| What | Proof |
|---|---|
| **#778 → #776: Debian 11 archive fix on all three workflows** (PR, continuous, tag) + generator emits the identical step | commits `7ce880d`; #776's debian11 job passes with the same step |
| **Critical CodeQL finding in #776 fixed** — `cla-check.yml` (`pull_request_target`) checked out PR-controlled code with a write token; restored `ref: main` | commit `1e53498`; CodeQL `actions/untrusted-checkout/critical` at `cla-check.yml:24` |
| #778 merged into #776's branch | `f48caff` — merged without human review; flagged (D16, N18) |
| **P5 measured** (debug build, no API key, no model): startup 9 ms; `cx ask` pattern matches ~54 ms median; "install docker" → "No AI backend" in ~49 ms (fails fast, no LLM wait) | timing harness, 10 runs each |
| **P5 finding:** the GUI Tab-completion module (`ModernInput`) is never instantiated — no Tab moment in the running product | `grep` for `ModernInput`/`InputConfig` outside `wezterm-gui/src/input/` → 0 uses |
| **#775 reviewed from the diff + sandbox tests** — gate logic correct; firejail/bwrap block `sudo` and network; bwrap runs in an ephemeral root and discards writes | [REVIEW_775.md](REVIEW_775.md) |
| Cloud session now pushes directly (B1, B5 resolved) | `git ls-remote origin ci/debian11-archive-all` → `7ce880d` |

### Corrected / owned
- The `build-docs` failure on #775 was a broken relative link this track introduced when its docs moved to `claude/`; #776 fixed it and this commit makes the identical change.
- `generate-workflows.py` is far behind the committed workflows (running it rewrites 27 files back to WezTerm names/repo and older actions). Noted in #778; nothing regenerated.

### Not done (and why)
- P8 not built here — #775 covers it (D12). P5b not built — contributor #763 covers it (D13).
- #775 review not posted publicly — outside limits (N17).
- No further merges after `f48caff` (D16).

### Next
- Day 3: after N16, confirm main's `debian11_continuous` goes green; re-check Dependabot; P6/P7 (#774 install smoke review, demo tape).

## Day 3 — Wed 2026-10-21 (11:25 MT)

### Shipped / verified
| What | Proof |
|---|---|
| **P6 — install.sh run end-to-end** in clean Ubuntu 24.04, Ubuntu 22.04 and Debian 12 containers (root + sudo user). Defects found and fixed in the repo that owns it: fallback installed Codaxy's unrelated npm `cx-cli`; Homebrew auto-install on macOS; non-Debian distros continued; on glibc < 2.39 or arm64 the script added the APT repo and then failed inside apt; the package ships no `cx` command although every suggestion runs `cx …`; quick start advertised commands that need AI without saying so | [cx-web #62](https://github.com/cxlinux-ai/cx-web/pull/62) `38ca57f` (into #60's branch). Before/after transcripts per distro; `shellcheck` clean; vitest 10/10 |
| **Real local AI validated for the first time in this week's runs** — `cx ai download` fetched `cxlinux-ai-7b-Q4_K_M.gguf` from HuggingFace in 2 m 57 s and `cx ask` answers offline | `cx ask 'how do I check disk usage'` → `df -h`, `du -sh *` |
| **Defect found and fixed: every AI answer was unusable.** The local model's JSON was printed raw, and `-d` never found a command in any AI answer (local, Claude or Ollama) because execution only reads the top-level `command` field that pattern matches produce | [#780](https://github.com/cxlinux-ai/cx-core/pull/780) `3659a86`: new `ask_response.rs` parser (11 tests); `echo y \| cx ask -d 'show memory usage'` runs `free -h` |
| Local answers made deterministic (greedy decoding) and llama.cpp teardown log removed from output | #780 `a5678ef`: 2 prompts × 2 runs → identical hashes |
| **P7 — 30-second demo recorded from the real model**, no mocks: question → commands; `-d` → plan, `[y/N]`, run; "install nginx" → package search, nothing installed | #780: `demo/cx-30s.tape`, `demo/record-30s.sh` (refuses without a real backend), `demo/cx-30s.gif` (29 s), transcript |
| Tests | `cargo test -p cx-terminal` 29/29 (18 + 11); fmt clean |

### Findings
- **Latency:** 45–62 s per local answer on a 2-vCPU VM, CPU-bound (`n_threads` hard-coded to 4; release build no faster). The GIF cuts the wait and keeps `time` on screen. Laptop latency not measured (N24).
- **All four pattern targets are stubs.** `cx new`, `cx save`, `cx restore`, `cx snapshots` print "not yet implemented" and exit 0. They also exist only under `cx-terminal cli …`, so the 35 pattern templates (`cx new python {name}` etc.) fall through to the AI catch-all, and `cx new python demo` passes the name positionally where the command expects `--name`. Day 1's note "CX-native intents already resolve offline" was wrong: they resolve to stubs. Not fixed this cycle (D19, N23).
- **#775's execution gate never sees a real AI command** — it keys on the same `command` field; its demo works only through `CX_ASK_MOCK_RESPONSE`. Added as item 5 of [REVIEW_775.md](REVIEW_775.md).
- `cx ask` exits 0 when no AI backend is available, so scripts can't detect the failure.
- `test_query_local_missing_model` fails on any machine that has the model downloaded (pre-existing).
- The model's tools (`search_packages`, `kb_lookup`, …) have no runtime in the CLI; #780 maps them to read-only commands.

### Not done (and why)
- No merges (D16). #780 and cx-web #62 await review.
- Stub commands not implemented: product scope (N23).

### Next
- Day 4: re-rank the plan around #780 (real AI path) and #775 rebase; P9 brand sweep prep.

## Day 4 — Thu 2026-10-22 (11:25 MT)

### Health check (verified against GitHub)
- No merges since Day 3. Open and waiting: cx-core #776, #779, #780; cx-web #60, #62. The parallel run updated #777 (docs) today.
- [#780](https://github.com/cxlinux-ai/cx-core/pull/780): every check green except `debian11` (fixed by #776). Required checks (Cargo Check, Rustfmt, Test Suite, Documentation Tests) pass; CodeRabbit, SonarCloud, CodeQL pass.
- `main` scheduled workflows green.

### Shipped / verified
| What | Proof |
|---|---|
| **P8 — dry-run-by-default package guard** (`package_guard.rs`): classify → `apt-get -s` preview → `[y/N]` (EOF = No) → exact argv, no shell → audit + transaction with undo. Wired into `cx ask -d` and `cx install` | [#781](https://github.com/cxlinux-ai/cx-core/pull/781) `848f401` |
| Tests prove nothing executes without consent: EOF; any reply but yes; failed preview even with `-y`; empty plan; dpkg/snap without consent. Hidden package changes refused (pipe, `;`, `$( )`, redirect, env prefix, `sudo -E`, apt `-o`, aptitude) | `cargo test -p cx-terminal` 44/44 (15 new) |
| **Real apt E2E in a clean Ubuntu 24.04 container**: preview `Install (1): hello` → EOF declined → consent installed `hello` → recorded undo `apt-get remove hello` → undo removed it | ignored test `real_apt_preview_execute_and_undo` with `CX_GUARD_E2E=1`, output in #781 |
| Plan re-ranked from evidence | PLAN.md "Re-rank (Day 4)" |

### Findings
- The local model answers install requests with a package *search*, not an install command, so with the local model the guard is reached only via Claude/Ollama answers or future offline intents (#763).
- Contributor PR #765 already implements `cx new` templates (opened in May, unreviewed). It is relevant to the stub-command finding (N23).
- #763/#764/#765 have no merge base with current `main` (branched before #771); they need rebases regardless.

### Not done (and why)
- No merge of #781 (D21). It is stacked on #780, so the merge order is #780 → #781.

### Next
- Day 5: P9 brand sweep; real-diff review of #765 against N23.

## Day 5 — Fri 2026-10-23 (11:25 MT)

### Health check
- No merges since Day 3 in any repo. Open from this track: cx-core #779, #780, #781 (+ new #782); cx-web #62 (+ new #63); cx-distro new #84. Parallel run updated #777 today.

### P9 brand sweep — `git grep -i cortex` on default branches, vendored code excluded
| Repo | Hits before | What they are | Action |
|---|---|---|---|
| cx-distro | 20 in 20 files | 19 installer slides linking the dead legacy org (`github.com/cortexlinux/cx-distro` → error; `cxlinux-ai/cx-distro` → 200) + a stale `.gitignore` path | **Fixed:** [cx-distro #84](https://github.com/cxlinux-ai/cx-distro/pull/84) → 0 hits |
| cx-core | 11 in 7 files | `sonar-project.properties` key/org = the live SonarCloud project (`cortexlinux_cortex`, analysed 2026-10-19); copilot-agent blocklists that *forbid* the legacy name; factual notes (Stripe product names, redirects) | Sonar needs a SonarCloud-side rename first (N31, D22); blocklists and factual notes kept (D22) |
| cx-web | 526 in 11 files | all in `docs/` — a Docusaurus site documenting the **retired Python CLI** (`cortex install`, `CORTEX_*` env vars, `~/.cortex/`). The live site (`client/`) has 0 hits | Not find-and-replaced: it would invent `CX_*` variables and paths that don't exist (D23, N32) |
| cx-docs (private) | 242 in 15 files | MkDocs architecture/runbooks for the same retired stack (`/etc/cortex`, `cortex_db`) | Same as cx-web docs (D23, N32) |
| Public issue text | 34 of 40 open cx-distro issues; cx-core #424/#425/#428 | epics and bounty descriptions | Company communication → N30 |

### Shipped / verified
| What | Proof |
|---|---|
| cx-distro installer links repointed to the live org | [cx-distro #84](https://github.com/cxlinux-ai/cx-distro/pull/84); `git grep -i cortex` → 0; all 19 HTML files parse |
| **README made true** — binary name, real subcommands, verified platforms only, no false sandbox/audit claims | [cx-core #782](https://github.com/cxlinux-ai/cx-core/pull/782); commands checked against `cx-terminal --help` |
| **Found: docs.cxlinux.com is down.** DNS → `cxlinux-ai.github.io`; HTTP 404; HTTPS cert `*.github.io` (browser error). Linked from the live install.sh (fixed in cx-web #62), the account page, the font error messages in cx-core and 19 installer slides | `curl -v` 2026-10-23 |
| Account page "Documentation" → `/getting-started` | [cx-web #63](https://github.com/cxlinux-ai/cx-web/pull/63); tsc clean, vitest 19/19 |
| **#765 (`cx new`) reviewed empirically** — templates generate and run (rust, go, node, python with real venv); path escape and non-empty dir refused. Missing `express`/`db` templates that `cx ask` patterns use | PR_REVIEWS.md refresh |
| **Found:** `cx-terminal cli new/save/restore/snapshots` connect to the mux server first and exit 1 without one, so they can't work on a fresh install even once implemented | run on current main |
| BOUNTY_AUDIT.md and PR_REVIEWS.md refreshed against live GitHub — no bounty or contributor-PR change since 2026-10-19; $50 still owed; one more unanswered contributor question (cx-distro #34) | both files, "Refresh — 2026-10-23" |

### Next
- Day 6: P10 evidence pack; independent verification pass over this week's PRs.
