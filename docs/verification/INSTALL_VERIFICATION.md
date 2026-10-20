# APT clean-install verification (2026-10-19)

Commands follow [README.md](../../README.md) **APT Repository (Recommended)** exactly.

**Summary:** see [VERIFICATION_SUMMARY.md](./VERIFICATION_SUMMARY.md). Raw logs: CI artifact `verification-logs` on PR [#774](https://github.com/cxlinux-ai/cx-core/pull/774).

## Ubuntu 24.04 — **PASS**

| Step | Result |
|------|--------|
| `curl -fsSL https://repo.cxlinux.com/key.gpg \| gpg --dearmor -o /etc/apt/keyrings/cxlinux.gpg` | PASS |
| Add `deb [signed-by=…] https://repo.cxlinux.com/apt stable main` | PASS |
| `apt-get install cx-terminal` | PASS |
| Package version | `20260223-145346-e97bbc7b` (deb `0.3.2` lineage) |
| `cx-terminal --version` | `cx-terminal 20260223-145346-e97bbc7b` |
| `cx-terminal --help` | PASS (ask, install, setup, what, fix, ai, …) |
| `cx --version` / `cx --help` | **FAIL** on published package — no `/usr/bin/cx` (fixed in `ci/deploy.sh` postinst for next release) |
| `cx-terminal activate` | **FAIL** on published build — subcommand missing at top level (fixed in `wezterm/src/main.rs`) |
| `cx-terminal cli activate` | Published build fails spawning `wezterm-mux-server` (package ships `cx-mux-server`; fixed in this PR) |

## Debian 12 (bookworm) — **FAIL** (published APT)

`apt-get install cx-terminal` errors:

```
cx-terminal : Depends: libc6 (>= 2.39) but 2.36-9+deb12u14 is to be installed
              Depends: libssl3t64 (>= 3.0.0) but it is not installable
              Depends: libx11-xcb1 (>= 2:1.8.7) but it is not going to be installed
E: Unable to correct problems, you have held broken packages.
```

**Blocker:** publish a Bookworm-built `.deb` (or lower glibc/openssl deps) before advertising Debian 12 APT support. This PR adds a **local/CI** Bookworm minimal CLI package only.

## CI

Workflow [`.github/workflows/apt-install-smoke.yml`](../../.github/workflows/apt-install-smoke.yml) runs the same steps on `ubuntu-24.04` (required) and `debian:12` in Docker (`continue-on-error: true` until packaging is fixed).
