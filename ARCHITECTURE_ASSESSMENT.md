# CX-Distro Architecture Assessment

**Repository:** `cxlinux-ai/cx-distro`
**Assessed:** 2026-02-06
**Assessor:** Agent Swarm Orchestrator

---

## 1. Project Overview

CX Distro is a **Debian 13 (Trixie)**-based Linux distribution builder for CX Linux, an AI-native operating system. It produces bootable ISO images via `live-build` and manages a signed APT package repository.

- **Base:** Debian 13 (Trixie)
- **Architecture:** amd64 (arm64 planned)
- **Version:** 0.1.0
- **License:** BSL 1.1 (CX additions), Apache 2.0 (infrastructure)
- **Maintainer:** AI Venture Holdings LLC

---

## 2. Directory Structure

```
cx-distro/
├── .github/workflows/         # CI/CD pipelines (build-iso, installation-tests)
├── packages/                  # Debian meta-packages
│   ├── cx-archive-keyring/    # GPG keyring for APT trust
│   ├── cx-core/               # Minimal system meta-package
│   ├── cx-full/               # Complete system meta-package
│   ├── cx-gpu-nvidia/         # NVIDIA GPU enablement
│   ├── cx-gpu-amd/            # AMD GPU enablement
│   ├── cx-llm/                # Local LLM inference runtime
│   ├── cx-secops/             # Security operations tools
│   └── cortex-branding/       # Distribution branding (plymouth, grub, wallpaper)
├── src/                       # Build system
│   ├── build.sh               # Main ISO build orchestrator (36KB)
│   ├── args.sh                # Build configuration variables (11KB)
│   ├── shared.sh              # Shared utility functions
│   ├── upgrade.sh             # Version upgrade script
│   ├── mods/                  # 56 sequential system modification scripts
│   └── styles/                # UI styling resources
├── config/                    # Release configuration (JSON)
├── scripts/                   # Dependency installation scripts
├── apt/                       # APT repository management
│   ├── conf/distributions     # reprepro configuration
│   ├── scripts/sign-release.sh
│   ├── cxlinux.sources        # DEB822 format repo config
│   └── cxlinux.list           # Legacy format repo config
├── tests/                     # Installation test suite
│   └── installation-tests.sh  # P0 verification tests (16KB)
├── Makefile                   # Build automation targets
├── clean_all.sh               # Full cleanup script
└── README.md                  # User documentation
```

---

## 3. Build System

### 3.1 Live-Build Pipeline

The build system uses Debian `live-build` to create hybrid ISO images:

- **Entry point:** `make iso` → `src/build.sh`
- **Configuration:** `src/args.sh` (env vars), `config/release-amd64.json` (locale)
- **Output:** `cx-linux-VERSION-amd64-offline.iso` with SHA256/SHA512 checksums

**Build Flow:**
1. Bootstrap Debian via `debootstrap`
2. Mount virtual filesystems into chroot
3. Apply 56 sequential modification scripts (`src/mods/NN-*/install.sh`)
4. Install kernel, bootloader, firmware
5. Generate squashfs + hybrid ISO

### 3.2 Package Build System

All packages use standard Debian packaging (`dpkg-buildpackage`):
- `debian/control` — metadata and dependencies
- `debian/changelog` — version tracking
- `debian/rules` — debhelper-based build rules
- `debian/postinst|prerm|postrm` — installation hooks

**Build:** `make package` or `make package PKG=cx-core`

### 3.3 APT Repository

- **Backend:** reprepro
- **Distributions:** `cx` (stable), `cx-testing`
- **Signing:** GPG key `9FA39683613B13D0`
- **Hosting:** GitHub Pages at `repo.cxlinux.com`
- **Formats:** DEB822 (`cxlinux.sources`) and legacy (`cxlinux.list`)

---

## 4. CI/CD Pipelines

### build-iso.yml
- **Triggers:** Push to main, version tags, manual dispatch
- **Jobs:** build-packages → build-iso → release (on tags)
- **Artifacts:** ISO, checksums, SBOM, packages

### installation-tests.yml
- **Triggers:** Push to main/develop, PRs, manual dispatch
- **Jobs:** ubuntu-install, debian-install, gpu-support (conditional), upgrade-test
- **Coverage:** GPG key import, repo config, package install/uninstall, signature verification

---

## 5. Modification System (Mods)

56 numbered scripts in `src/mods/` that customize the base system:

| Range | Category | Examples |
|-------|----------|----------|
| 00-10 | System Setup | APT sources, hostname, systemd, kernel |
| 10-20 | Package Management | Remove snap, install GNOME apps, Firefox, fonts |
| 21-25 | Installer | Ubiquity patches, wallpaper |
| 26-45 | GNOME Desktop | Extensions, dash-to-panel, ArcMenu, dconf |
| 78-88 | Cleanup | Remove ads, clean cache, wipe history |

---

## 6. Security Posture

- **Repository signing:** GPG-signed Release files
- **Package trust:** `cx-archive-keyring` distributes public key
- **ISO integrity:** SHA256 + SHA512 checksums
- **System hardening:** AppArmor, Firejail, nftables, fail2ban
- **SBOM:** CycloneDX and SPDX generation via `syft`

---

## 7. Key Observations

### Strengths
- Well-structured modular build system
- Comprehensive CI/CD with multi-distro testing
- Proper Debian packaging standards
- Security-conscious design (signed packages, SBOM)

### Areas of Concern
1. **Branding inconsistency:** `src/args.sh` still references "cortex" (`TARGET_NAME="cortex"`, `TARGET_BUSINESS_NAME="Cortex Linux"`) despite rebrand to CX Linux
2. **Ubuntu vs Debian confusion:** `args.sh` targets Ubuntu Plucky (25.04) but Makefile targets Debian Trixie (13) — dual-target strategy needs clarity
3. **No automated syntax validation:** No shellcheck/yamllint in CI for the 56 mod scripts
4. **Missing preseed files:** Referenced in docs but not present in repo
5. **Some PRs overlap with issues:** #60, #61, #62 exist as both open issues and open PRs

---

## 8. Technology Stack

| Component | Technology |
|-----------|-----------|
| Base OS | Debian 13 Trixie / Ubuntu 25.04 Plucky |
| ISO Builder | live-build + debootstrap |
| Package Format | .deb (debhelper 13) |
| Repository | reprepro + GitHub Pages |
| CI/CD | GitHub Actions |
| Signing | GnuPG (key 9FA39683613B13D0) |
| SBOM | syft (CycloneDX + SPDX) |
| Desktop | GNOME with extensions |
| Boot | GRUB (EFI) + syslinux (BIOS) |
