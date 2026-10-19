# Blockers

Logged only after at least three approaches were tried. Each names what would unblock it.

## B1 — Cloud session cannot push to `cxlinux-ai` (worked around)
- **Tried:** (1) session GitHub App via `add_repo … access: push` → push refused, app not installed on the org; (2) `GH_TOKEN` in the cloud environment → invalid token; (3) repository-scoped API through the session proxy → access not enabled for org repos other than the attached one.
- **Workaround in use:** commit and push from a scratch clone on Mike's Mac with its authenticated `gh` (DECISIONS D7). Works while the Mac is awake and the desktop app is open.
- **Unblock permanently:** NEEDS_MIKE N6 (install the Claude GitHub App on `cxlinux-ai`).

## B2 — Expired CI logs for March–May failures
- **Tried:** `gh run view --log-failed` for runs 23110754863 (CX Terminal Build, main) and 25201523786 (Dependabot) → HTTP 410 / empty; job-level log API → same retention cut-off; re-reading the workflow to infer the failing step.
- **Impact:** root cause of the red `CX Terminal Build` on main must be re-derived from a fresh run.
- **Unblock:** the Day 1 cycle 2 run re-triggers CI on the P1 PR and reads current logs.
