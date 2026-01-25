# Claude Worker: Integration & Testing

## Your Assignment
You are responsible for **Integration, Testing, and Polish**.

## Scope
```
shell-integration/       ✅ Done - Shell scripts
docs/                    ⏳ Ongoing - Documentation
tests/                   ⏳ YOUR TASK - Integration tests
examples/                ⏳ YOUR TASK - Example configs
```

## Your Tasks

### 1. Build Verification (P0)
- Run `cargo check` and fix any compilation errors
- Run `cargo build` and verify binaries created
- Run `cargo test` and ensure tests pass
- Document any build issues

### 2. Integration Tests (P1)
Create tests that verify:
- OSC sequences parsed correctly
- Block lifecycle (start → output → end)
- AI panel toggle
- Shell integration scripts work

### 3. Example Configurations (P0)
Create in `examples/`:
- `cx-minimal.lua` - Bare minimum config
- `cx-full.lua` - All features enabled
- `cx-themes.lua` - Theme customization examples

### 4. Documentation (P1)
Update/create:
- `docs/INSTALL.md` - Build and install instructions
- `docs/CONFIG.md` - Configuration reference
- `docs/KEYBINDINGS.md` - Default key bindings
- `README.md` - Keep updated

### 5. CI Setup (P2)
Create `.github/workflows/`:
- `build.yml` - Build on push
- `test.yml` - Run tests
- `release.yml` - Create releases

## Key Commands
```bash
# Verify compilation
cargo check 2>&1 | head -100

# Build
cargo build 2>&1 | tail -50

# Test
cargo test 2>&1

# Run locally
cargo run --bin cx-terminal-gui
```

## Success Criteria
- [ ] `cargo build` succeeds
- [ ] `cargo test` passes
- [ ] Example configs work
- [ ] Documentation is accurate
- [ ] CI pipeline runs

## Do NOT Touch
- Block rendering code (another worker)
- AI panel code (another worker)
- Core WezTerm functionality

## Communication
Maintain `docs/BUILD_STATUS.md` with:
- Current build status
- Errors encountered and fixes
- Test results
- Integration issues found
