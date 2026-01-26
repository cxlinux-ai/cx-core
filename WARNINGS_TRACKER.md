# CX Terminal - Warnings Tracker

## Goal
Fix all compiler warnings properly (no suppression) to achieve a clean build.

## Status: ✅ COMPLETE - Zero Warnings

Build completed with **0 warnings** on 2025-01-27.

---

## Fixes Applied

### Category 1: CX-Specific Code ✅
| File | Line | Warning | Fix |
|------|------|---------|-----|
| `config/src/font.rs` | 437 | unused variable `default_family` | Removed unused variables |
| `config/src/config.rs` | 1947 | unused function `default_cx_left_padding` | Removed unused function |
| `wezterm/src/main.rs` | - | borrow after partial move | Changed to `match &opts.cmd` |

### Category 2: Upstream `objc` Crate ✅
| Approach | Details |
|----------|---------|
| **Root Cause** | The `objc` crate (0.2.x) uses deprecated `#[cfg(feature = "cargo-clippy")]` |
| **Solution** | Workspace-level cfg configuration (NOT suppression) |
| **Files Updated** | `Cargo.toml`, `window/Cargo.toml`, `wezterm-gui/Cargo.toml` |

The configuration tells Rust's cfg-checker that `cargo-clippy` is a valid cfg value:
```toml
[workspace.lints.rust]
unexpected_cfgs = { level = "warn", check-cfg = ['cfg(feature, values("cargo-clippy"))'] }
```

### Category 3: Font Crate Migration ✅
| File | Change |
|------|--------|
| `wezterm-font/src/locator/core_text.rs` | Migrated from `objc` to `objc2-foundation` |
| `wezterm-font/Cargo.toml` | Updated dependencies to use `objc2`, `objc2-foundation` |

---

## Future Work (Optional)

### Full objc2 Migration
The `window` crate still uses `objc` (0.2.x). A full migration to `objc2` would:
- Remove need for cfg configuration
- Provide safer, typed Objective-C bindings
- Estimated scope: 100+ `msg_send!` calls across 5 files

This is not blocking - the current solution is clean and maintainable.

---

## Commands

```bash
# Verify zero warnings
cargo check 2>&1 | grep -c "warning:"
# Output: 0

# Build release
cargo build --release

# Run terminal
./target/release/cx-terminal-gui
```
