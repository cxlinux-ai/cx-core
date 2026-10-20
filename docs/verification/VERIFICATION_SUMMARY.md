# Install & license verification summary

Evidence for PR [#774](https://github.com/cxlinux-ai/cx-core/pull/774). Full transcripts are **CI artifacts**, not committed logs.

## How to reproduce locally

| Check | Command |
|-------|---------|
| Ubuntu APT (published repo) | `bash ci/apt-install-smoke.sh ubuntu` |
| Debian 12 APT (expected fail until Bookworm deb published) | `bash ci/apt-install-smoke.sh debian` |
| Bookworm minimal `.deb` build | `MINIMAL_DEB=1 bash ci/build-deb-bookworm.sh` |
| Bookworm `.deb` install smoke | `bash ci/test-deb-bookworm.sh cx-terminal-*.debian12-minimal.deb` |

## CI workflows

| Workflow | What it proves |
|----------|----------------|
| [apt-install-smoke.yml](../../.github/workflows/apt-install-smoke.yml) | Official `repo.cxlinux.com` install on Ubuntu 24.04 (required); Debian 12 (`continue-on-error` until Bookworm package ships). |
| [debian12-deb-smoke.yml](../../.github/workflows/debian12-deb-smoke.yml) | Build minimal CLI `.deb` in `debian:12`, install in fresh container, `cx --version` / `cx activate --help`. |

Download **verification-logs** and **cx-terminal-deb-bookworm** artifacts from the latest PR run for raw transcripts.

## Results (2026-10-19 agent run)

### Ubuntu 24.04 APT — **PASS**

- GPG key + `stable main` list entry: OK
- `apt-get install cx-terminal`: OK (`20260223-145346-e97bbc7b`)
- `cx-terminal --version` / `--help`: OK
- Published package gaps (fixed in this PR for next release): no `/usr/bin/cx` symlink; top-level `activate` missing; mux binary name mismatch

### Debian 12 APT (published) — **FAIL** (expected)

- `libc6 (>= 2.39)` vs Bookworm `2.36`; `libssl3t64` not installable on current published deb
- **Mitigation in PR:** build minimal Bookworm-linked CLI `.deb` in CI (not published to APT)

### Bookworm minimal CLI `.deb` — **PASS**

- `MINIMAL_DEB=1` build on `debian:12`
- `dpkg -i` + deps in fresh container
- `cx --version`, `cx activate --help`, `cx license activate --help` (alias)
- `cx activate` with invalid key → `❌ Activation failed: Invalid license key` (exit 1) against live `license.cxlinux.com`

### Full GUI `.deb` (`ci/deploy.sh` on Bookworm)

- **Previously failed** when `deps/freetype/{zlib,libpng,freetype2}` submodules were empty: `cc` could not find `zlib/*.c` (silent `git submodule update` from wrong cwd).
- **Fix in this PR:** explicit submodule init in `ci/build-deb-bookworm.sh` + `deps/freetype/build.rs` probes source files and inits from repo root. Re-verify via optional CI job `full-gui-deb` artifact.

### Valid license key

Not exercised (no Stripe test key). Flow documented in [LICENSE_ACTIVATION_FLOW.md](./LICENSE_ACTIVATION_FLOW.md).

## Related docs

- [INSTALL_VERIFICATION.md](./INSTALL_VERIFICATION.md) — checklist
- [DEBIAN12_BOOKWORM_DEB.md](./DEBIAN12_BOOKWORM_DEB.md) — Bookworm packaging
- [LICENSE_ACTIVATION_FLOW.md](./LICENSE_ACTIVATION_FLOW.md) — `cx activate` API steps
- [CX_WEB_COPY_TODO.md](./CX_WEB_COPY_TODO.md) — site copy alignment
