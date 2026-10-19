# Decisions Log

Each entry: what was chosen, why, how to undo. Reversible, consistent with existing code, backed by evidence.

## D1 — Canonical org/repo is `cxlinux-ai` / `cxlinux-ai/cx-core` (resolves FR-001)
- **Chose:** treat `cxlinux-ai` as canonical for all GitHub work; `cx-core` as the product repo.
- **Why:** live GitHub state, not memory. The legacy org handle no longer resolves; `cxlinux-ai/cx`, `cxlinux-ai/cortex` and the legacy repo path all redirect to `cxlinux-ai/cx-core` (identical HEAD `bf87c78`).
- **Undo:** none needed — this records reality. If Mike intends a different canonical repo, update this entry and PLAN.md.

## D2 — The product is now Rust (`cx-terminal` crate, WezTerm-based), not the Python apt wrapper in the older spec
- **Chose:** plan, build and verify against the Rust codebase on main. The spec's `pytest tests/` / `pip install -e .` workflow and Python package layout no longer apply to cx-core.
- **Why:** `README.md`, `Cargo.toml`, and 760+ PR history; the Python-era repos are archived (`cx-cli`, `apt-repo`).
- **Undo:** n/a. Flagged in NEEDS_MIKE so the project spec can be updated.

## D3 — Remove the private `hrm-ai` git dependency from the public manifest (P1)
- **Chose:** delete `hrm-ai = { git = "…/hrm-ai-standalone.git", optional = true }` from `wezterm/Cargo.toml`; keep the `hrm` feature declared (`hrm = ["dep:sqlx"]`); leave all `#[cfg(feature = "hrm")]` code untouched.
- **Why:** Cargo fetches every git dependency (optional or not) to resolve a workspace. The source repo is private, so every clone outside Mike's account fails with HTTP 401 before compiling a single crate. Default builds never use `hrm-ai`. This is the smallest change that restores public buildability without making anything public.
- **Trade-off:** `--features hrm` no longer works from the public repo alone; premium builds re-add the dependency in a private overlay (the commented line in the manifest shows exactly what to add).
- **Undo:** `git revert <commit>` restores the line; nothing else changed.

## D4 — Contributor bounty PRs are never merged autonomously
- **Chose:** review, document, and queue; do not merge.
- **Why:** policy is pay-on-merge, so a merge is a spending commitment (hard limit).
- **Undo:** n/a.

## D5 — No public comments, reviews, or issue edits on contributor threads this week
- **Chose:** draft all contributor-facing text in NEEDS_MIKE.md; post nothing.
- **Why:** those are communications as the company (hard limit); editing bounty text also changes financial commitments.
- **Undo:** n/a.

## D6 — Code merges to main only after CI green; docs merges any time
- **Chose:** docs-only PRs merge immediately; PRs touching `*.rs`/`Cargo.*` merge only with green CI and a logged revert path. No `v*` tags.
- **Why:** `cx-build.yml` ignores `docs/**` and `*.md`; `*_continuous.yml` workflows build packages on Rust/Cargo changes to main (reversible — next build supersedes); `cx-release.yml` fires on `v*` tags (not reversible in practice).
- **Undo:** revert the merge commit; continuous builds rebuild from the reverted tree.

## D7 — Push path is Mike's Mac via the desktop bridge
- **Chose:** edit and verify in the cloud workspace; commit and push from a scratch clone at `/tmp/cx-autonomy/cx-core` on the Mac using its authenticated `gh`.
- **Why:** the cloud session's GitHub App is not installed on `cxlinux-ai` (push refused); the Mac's `gh` is authenticated as `mikejmorgan-ai` with `repo` scope.
- **Undo:** n/a. Installing the Claude GitHub App on the org (NEEDS_MIKE N6) removes the dependency on the Mac being awake.

## D8 — EOF on a `[Y/n]` prompt is a refusal, not consent
- **Chose:** in `AskCommand::execute_cx_command`, treat `read_line` returning 0 bytes (EOF) as "do not run"; keep Enter/`y` as yes for interactive use; `-d -y` still auto-executes.
- **Why:** reproduced on 2026-10-19 — `cx ask "save my work" </dev/null` printed the prompt and then **executed** the command, because EOF yields an empty string and empty meant yes. Safe-by-default execution is a stated product differentiator (spec §8/§10).
- **Undo:** revert the commit; the helper `confirmed_default_yes` and 3 unit tests are the whole change.

## D9 — Repo `.claude/CLAUDE.md` says "Don't push to main without user approval"
- **Chose:** never push directly to main; all changes land through PRs. Docs PRs and CI-green code PRs are merged under Mike's standing merge authority (Aug 16 2026) and this week's mandate.
- **Why:** reconciles the repo rule (no direct pushes) with the standing authority (merging PRs).
- **Undo:** n/a.
