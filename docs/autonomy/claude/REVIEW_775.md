# Review — PR #775 "dry-run-by-default cx ask + safety audit/undo"

**Date:** 2026-10-20 · **Method:** full `gh pr diff 775` read, plus empirical sandbox tests in a clean Ubuntu 24.04 environment as a non-root user with passwordless sudo (firejail 0.9.72, bubblewrap 0.9.0), using the exact arguments from the diff.
**Status:** not posted to GitHub — posting a public review is queued for Mike (NEEDS_MIKE N17).

The gate logic is solid; the sandbox breaks the product's core action. Recommend fixing items 1–2 before merge.

## What's good
- `execution_gate` / `effective_auto_confirm`: preview by default, `-y` ignored without `--execute`, `[y/N]` everywhere, EOF never consent — all unit-tested.
- Audit log and transaction records; undo refuses when cwd metadata is missing.
- PR body states plainly that AppArmor is not implemented.

## 1. Blocking — package installs cannot run inside either sandbox
Every state-changing command goes through `run_sandboxed_shell`, including `sudo apt install …` — CX's primary action.

| Inside sandbox | firejail (`--private-tmp --net=none --caps.drop=all`) | bwrap (`--unshare-all`, read-only binds) |
|---|---|---|
| `sudo -n true` | `sudo: Permission denied` | `The "no new privileges" flag is set, which prevents sudo from running as root` |
| network | none | none |
| `apt-get install -s hello` | — | fails; `/var/lib/dpkg` not mounted |

Repro (as a sudo-capable non-root user):
```bash
firejail --quiet --private-tmp --net=none --caps.drop=all -- sh -c 'sudo -n true && echo OK || echo FAIL'
bwrap --ro-bind /usr /usr --ro-bind /bin /bin --ro-bind /lib /lib --ro-bind /lib64 /lib64 --ro-bind /etc /etc --proc /proc --dev /dev --tmpfs /tmp --unshare-all -- sh -c 'sudo -n true; apt-get install -s hello'
```
Effect: installing the recommended sandbox makes `cx install docker --execute` fail for every user.

**Suggested shape:** privileged package operations (`apt`, `apt-get`, `dpkg`, `snap` under `sudo`) bypass the sandbox. Preview with a real simulation (`apt-get -s install …`), show the plan, run on the host after `[y/N]`, and record the transaction plus undo (`apt-get remove` of what the simulation reported). Keep the sandbox for unprivileged AI-suggested shell text.

## 2. Blocking — bwrap runs commands in an ephemeral root (silent success)
`run_bubblewrap_in` doesn't bind the cwd or `$HOME`, so the process starts in `/` of a throwaway root. File writes succeed and are then discarded:
```
cwd=/home/cxtest  →  inside bwrap: pwd = /   touch ./cx-marker → "succeeds", gone after exit
```
Affects `cx new`, `cx save`, and `cx undo` (undo is then marked done having done nothing). Fix: `--bind <cwd> <cwd> --chdir <cwd>` (decide `$HOME` rw vs ro), or fail closed when the cwd isn't visible inside the sandbox.

## 3. Hardening — `is_read_only_cx_cli` uses `starts_with`
Commands run via `sh -c`, so `cx snapshots -l; <anything>` would be classed read-only and run without `--execute`. Not reachable today (read-only templates take no user text), but an exact match against the template list, or rejecting `; & | $ \` > <` and newlines, costs one line.

## 4. CI on #775
All three failures (CLA for `cursoragent`, `debian11`, `build-docs`) are fixed by #776 with #778 merged into it. The `build-docs` failure was a broken relative link in `docs/autonomy/claude/` introduced by this track when its docs moved folders.

## 5. Blocking (found Day 3 with the real local model) — the gate never sees AI commands
`maybe_execute_from_response` reads only the top-level `command` field. Real backends put their answer in `response`: the CX model as JSON `{"summary", "commands": [{"command_template"}]}`, Claude/Ollama as Markdown. So with a real backend nothing is previewed, gated or audited; `demo/safety-demo.sh` passes only because `CX_ASK_MOCK_RESPONSE` supplies a top-level `command`. #780 adds `ask_response::commands_from_envelope`; after rebase, use it for AI answers in `maybe_execute_from_response`.
