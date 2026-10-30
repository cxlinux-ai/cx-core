# CX safety claims — code verification (2026-10-20)

Branch: `cursor/safety-dry-run-demo-4556` (draft PR). PR #772 (**EOF is not consent**) is **merged on `main`** (`b1090ad13`).

## Claim matrix

| Claim | Verdict | Evidence | Test / transcript |
|-------|---------|----------|-------------------|
| **Dry-run by default** (`cx ask`) | **PASS** (this PR) | `wezterm/src/cli/execution_safety.rs`, `wezterm/src/cli/ask.rs` | Unit: `execution_gate` / `default_is_preview_only` in `execution_safety.rs` and `ask.rs` tests. Demo: `demo/safety-demo.sh` step 1 (`</dev/null`, no marker file). |
| **Non-interactive / EOF never executes** | **PASS** | All execution prompts use **`[y/N]`** (default **No**); EOF → `confirmed_default_no(None) == false` | Unit: `default_no_prompt_requires_explicit_y`, `eof_is_never_consent`. |
| **`-y` without `--execute`** | **PASS** | `effective_auto_confirm` + `execution_gate(false, true) == PreviewOnly`; stderr note in `AskCommand::run` | Unit: `y_without_execute_does_not_auto_confirm`. |
| **Explicit `--execute` + confirm or `-d -y`** | **PASS** | `AskCommand::execute`; `cx install`/`setup`/`fix` no longer imply `--execute` | Unit: `explicit_execute_flag_enables_run_path`. Demo step 2. |
| **Firejail / bubblewrap sandboxing** | **PASS** (with constraints) | `wezterm/src/cli/command_sandbox.rs` wraps `cx ask` / `cx undo` shell runs; **warns** and runs on host if neither tool is on PATH. Privileged package manager commands (`sudo apt/apt-get/dpkg/snap`) bypass sandbox after explicit confirmation. Bwrap and firejail bind cwd (read-write) and HOME (read-only), fail closed if cwd missing. | No AppArmor profiles. Privileged commands run on host by design (required for package operations). Set `CX_DISABLE_SANDBOX=1` to force host. Tests: `command_sandbox.rs::privileged_package_commands_detected`, `non_privileged_commands_not_detected`. |
| **Read-only command injection prevention** | **PASS** | `is_read_only_cx_cli` in `execution_safety.rs` uses exact string matching and rejects shell metacharacters (`;`, `&`, `|`, `$`, `` ` ``, `>`, `<`, newlines) | Unit: `read_only_rejects_command_injection` verifies `"cx snapshots -l; touch /tmp/x"` and similar injection attempts are rejected. |
| **AppArmor** | **FAIL** (not implemented) | No AppArmor integration in cx-core | N/A |
| **Transaction history + undo** | **PARTIAL → PASS for `cx ask`** | `wezterm/src/cli/ops.rs` (`transactions.jsonl`), `cx undo` | Demo step 4. `cx save`/`restore` remain stubs (`wezterm/src/cli/snapshot.rs`). Security patches: `wezterm/src/cli/security/patcher.rs::rollback_patch`. |
| **Audit log** | **PARTIAL** | CLI: `~/.cx/audit.log` via `ops.rs`, `cx audit`. Python alert manager: `cx/system_alert_manager.py` (`audit_operation` decorator) — separate subsystem. | Demo step 3. Python: `tests/test_system_alert_manager_enterprise.py::test_audit_logging`. |
| **Offline fallback** | **PARTIAL** | Pattern matcher + `CX_ASK_MOCK_RESPONSE` + local GGUF (`ask.rs::query_local`) + Ollama env | Without model/API, `query_ai` returns `no_ai` hint. Demo uses labeled mock. |
| **Clean uninstall / removable** | **PARTIAL** | Debian `prerm` removes alternatives (`ci/deploy.sh`); `cx clean-local-data` | `dpkg -r` for package; see `MODEL_DOWNLOAD_SOURCES.md` for HF default model (unchanged). |

## PR #774 coordination

Open draft [#774](https://github.com/cxlinux-ai/cx-core/pull/774) covers Debian Bookworm install + license activation. This branch stacks on **current `main`** and does not conflict with #774’s packaging docs; merge order: either PR first, then rebase.

## Run the demo

```bash
# Host (Ubuntu 24.04) or container:
./demo/safety-demo.sh

# Record proof:
asciinema rec -c './demo/safety-demo.sh' docs/safety/safety-demo.cast
```

Pre-built transcript (if cast not regenerated in CI): run the script and redirect to `docs/safety/safety-demo.log`.
