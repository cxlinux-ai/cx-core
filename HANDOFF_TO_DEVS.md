# CX-Distro: Agent Swarm Handoff to Engineering

**Date:** 2026-02-06
**From:** AI Agent Swarm (automated)
**To:** CX Linux Engineering Team

---

## What Just Happened

An automated agent swarm analyzed all 22 open issues on `cxlinux-ai/cx-distro`, triaged them, and resolved 8 of them in a single session. The changes are on branch `agent-swarm/issue-resolution` in the cx-distro repo, ready for your review.

## What Was Done (Ready for Review)

### Branch: `agent-swarm/issue-resolution` on cx-distro

**4 commits, 255 files changed.**

| Issue | What Changed | Risk Level |
|-------|-------------|------------|
| **#53 Rebrand Cortex -> CX** | 252 files: args.sh, 148 HTML slides across 14 languages, CI workflows, package controls, GNOME extensions, Plymouth/GDM configs, image assets renamed | **Medium** — verify build output names |
| **#61 SPDX License** | Added `SPDX-License-Identifier: BUSL-1.1` to LICENSE | **None** |
| **#51 Copilot Instructions** | New `.github/copilot-instructions.md` (264 lines) — build system docs, gotchas, workflows | **None** |
| **#54 CI Improvements** | Added QEMU smoke test job, SBOM generation step, manual dispatch inputs to build-iso.yml | **Low** — CI only |
| **#46 Calamares Installer** | New `src/mods/21-calamares-mod/` with install script, 6 module configs, branding, QML slideshow, desktop entry | **Medium** — needs live ISO test |
| **#59 Demo Scaffolding** | New `docs/demos/README.md` with asciinema recording setup and 3 demo scripts | **None** |
| **#60 Clone URL** | Fixed `cortex-distro.git` -> `cx-distro.git` in README | **None** |
| **#62 Domain Unification** | All `cortexlinux.com` -> `cxlinux.ai` across the repo | **Low** |

### What You Need To Do

1. **Review the branch.** `git diff main..agent-swarm/issue-resolution --stat` to see scope.
2. **Test the ISO build.** The rebrand changed `TARGET_NAME` from "cortex" to "cx" — this affects output filenames and OS identity files. Run `make iso` on a build host to verify.
3. **Test the Calamares mod.** Boot a live ISO and verify the installer launches from the desktop icon and the branding displays correctly.
4. **Merge or cherry-pick.** If you prefer incremental merges, the commits are atomic per-issue.

---

## What Was NOT Done (Needs Humans)

### Decisions Needed (No Code Can Fix These)

| Issue | Title | What's Blocking |
|-------|-------|----------------|
| **#3** | Debian base selection | **Are we Debian Trixie or Ubuntu Plucky?** `args.sh` says Ubuntu 25.04, Makefile says Debian 13. Pick one or document the dual-target strategy. |
| **#2** | APT trust model | Key rotation policy, offline mirror strategy, pinning rules — these are security policy decisions. |
| **#5** | GPU driver enablement | DKMS vs prebuilt modules? Secure Boot/MOK signing? Needs hardware testing on NVIDIA/AMD. |
| **#9** | Upgrade/rollback | Btrfs snapshots vs apt pinning vs custom tool? Design decision. |
| **#1** | First-boot provisioning | Preseed vs cloud-init? First-boot wizard UX? Product decision. |

### Missing Source Code

| Issue | Title | Problem |
|-------|-------|---------|
| **#55** | Build cx-core .deb | Is this the meta-package (already exists) or the cx-cli Python app? Where's the source? |
| **#56** | Build cx-stacks .deb | Python module source code is not in cx-distro. Which repo has it? |
| **#57** | Build cx-ops .deb | Same — source code location unknown. |

### Needs Live Environment

| Issue | Title | Problem |
|-------|-------|---------|
| **#58** | Test apt install on Ubuntu 24.04 | Needs a published APT repo with real packages to test against. |
| **#59** | Demo GIFs | Scaffolding is done, but recording requires a running CX Linux system. |

---

## Known Loose Ends

1. **Directory `packages/cortex-branding/` is still named with "cortex"** — contents are rebranded but the directory itself wasn't renamed to avoid breaking Makefile/CI references. Someone should do a `git mv packages/cortex-branding packages/cx-branding` and update the Makefile build loop.

2. **GNOME extension `.mo` locale files** still have `cortexlinux.com` baked into the compiled binary. These need recompilation from `.po` source files.

3. **No shellcheck in CI.** 56 mod scripts have zero automated syntax validation. Add a shellcheck step to the CI pipeline.

4. **CI artifact name changed** from `cortex-linux-*` to `cx-linux-*`. If any external systems (release scripts, download pages, CDN configs) reference the old name, they'll break.

---

## Suggested Assignments

| Task | Owner | Priority | Effort |
|------|-------|----------|--------|
| Review + merge agent branch | Senior Dev | P0 | 1 hour |
| Test ISO build with rebrand | Build Engineer | P0 | 2 hours |
| Decide Debian vs Ubuntu (#3) | CTO/Architect | P0 | 30 min decision |
| Rename cortex-branding dir | Any Dev | P1 | 15 min |
| Locate cx-cli/stacks/ops source (#55-57) | Tech Lead | P1 | 30 min |
| Test Calamares on live ISO (#46) | QA | P1 | 1 hour |
| Add shellcheck to CI | DevOps | P2 | 30 min |
| Record demo GIFs (#59) | Marketing/DevRel | P2 | 1 hour |
| Architecture decisions (#1,2,5,9) | CTO + Senior Eng | P1 | Half-day session |

---

## How To Inspect The Changes

```bash
# Clone and checkout the branch
git clone https://github.com/cxlinux-ai/cx-distro.git
cd cx-distro
git checkout agent-swarm/issue-resolution

# See what changed
git log --oneline main..HEAD
git diff main..HEAD --stat

# Verify no remaining cortex references
grep -ri "cortex" --include="*.sh" --include="*.yml" --include="*.md" --include="*.conf" --include="*.json" --include="*.html" . | grep -v ".git/" | grep -v "not.*Cortex"

# Build (on a Debian/Ubuntu host with deps)
make deps
make iso
```
