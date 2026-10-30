# Debian 12 Bookworm — local `.deb` build and install proof

## Goal

Produce a Bookworm-linked `cx-terminal` package (glibc 2.36 / OpenSSL 3 on Debian) without publishing to `repo.cxlinux.com`, then install it in a fresh `debian:12` container.

## Build

```bash
# On debian:12 (or Docker):
MINIMAL_DEB=1 bash ci/build-deb-bookworm.sh
# Artifact: cx-terminal-<TAG>.debian12-minimal.deb
```

Full GUI package (optional):

```bash
bash ci/build-deb-bookworm.sh   # runs ci/deploy.sh after GUI/mux builds
```

CI: `.github/workflows/debian12-deb-smoke.yml` (minimal build + install smoke). Optional `full-gui-deb` job uploads full `.deb` or build log on failure.

## Install test

```bash
bash ci/test-deb-bookworm.sh cx-terminal-*.debian12-minimal.deb
```

## Results

See [VERIFICATION_SUMMARY.md](./VERIFICATION_SUMMARY.md) for pass/fail matrix and CI artifact links.

| Step | Result |
|------|--------|
| Build `cx-terminal` on `debian:12` (`MINIMAL_DEB=1`) | **PASS** |
| `dpkg -i` in fresh `debian:12` | **PASS** |
| `cx activate` invalid key → server error (exit 1) | **PASS** |
| Full GUI `.deb` via `ci/deploy.sh` | See CI `full-gui-deb` job / summary (submodule init fix) |

### Valid license key (not exercised — no Stripe / no test key)

On success, `cx activate <KEY>` would:

1. `POST /api/v1/licenses/activate` with hardware fingerprint + hostname.
2. Save key to `~/.cx/license.key`.
3. `POST /api/v1/licenses/validate` and print tier, email, expiry, device limits, features.

See [LICENSE_ACTIVATION_FLOW.md](./LICENSE_ACTIVATION_FLOW.md).
