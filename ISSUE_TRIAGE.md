# CX-Distro Issue Triage

**Repository:** `cxlinux-ai/cx-distro`
**Date:** 2026-02-06
**Total Open Issues:** 22 (includes 5 that are also open PRs)

---

## Summary

| Category | Count | Issues |
|----------|-------|--------|
| GREEN (Ready for Agents) | 8 | #60, #61, #62, #51, #53, #54, #46, #59 |
| YELLOW (Needs Clarification) | 5 | #55, #56, #57, #58, #8 |
| RED (Blocked) | 9 | #1, #2, #3, #4, #5, #6, #7, #9, #46 (partial) |

**Note:** Issues #60, #61, #62, #53, #51 already have open PRs. Agent work on these
would either review/improve existing PRs or create fresh implementations if PRs are stale.

---

## GREEN (Ready for Agents)

These issues can be fully resolved with code/config changes in the repository.

### #60: fix: Correct clone URL from cortex-distro to cx-distro
- **Complexity:** Low
- **PR exists:** Yes (branch: `fix/correct-clone-url`)
- **What to do:** Update `README.md` clone URL from `cortex-distro.git` to `cx-distro.git`. Verified: README line 21 still contains the old URL.
- **Files:** `README.md`
- **Risk:** None — documentation-only change

### #61: docs: Add SPDX license identifier for BSL 1.1
- **Complexity:** Low
- **PR exists:** Yes (branch: `docs/spdx-license-identifier`)
- **What to do:** Add `SPDX-License-Identifier: BUSL-1.1` header to `LICENSE` file so GitHub and SBOM tools recognize the license type.
- **Files:** `LICENSE`
- **Risk:** None — metadata-only change

### #62: fix: Unify all domain references to cxlinux.ai
- **Complexity:** Medium
- **PR exists:** Yes (branch: `fix/unify-domain-references`)
- **What to do:** Audit all `.md` files and config files; replace inconsistent domain references (`cortexlinux.com`, mixed domains) with canonical `cxlinux.ai` domain. Confirmed: multiple files still reference old domains.
- **Files:** `README.md`, `packages/cortex-branding/debian/control`, `.github/workflows/*.yml`, `src/args.sh`
- **Risk:** Low — must ensure APT repo URLs remain functional (repo.cxlinux.com may differ from cxlinux.ai)

### #51: Add .github/copilot-instructions.md for agent onboarding
- **Complexity:** Low
- **PR exists:** Yes (draft, branch: `copilot/add-copilot-instructions-file`)
- **What to do:** Create `.github/copilot-instructions.md` documenting build system, package building, ISO building, project layout, CI/CD, and gotchas. This is a pure documentation addition.
- **Files:** `.github/copilot-instructions.md` (new file)
- **Risk:** None — additive documentation only

### #53: [WIP] Rebrand to CX Linux
- **Complexity:** High
- **PR exists:** Yes (draft, branch: `rebrand`)
- **What to do:** Complete the rebrand from "Cortex" to "CX" across the entire codebase. Confirmed remaining issues:
  - `src/args.sh`: `TARGET_NAME="cortex"`, `TARGET_BUSINESS_NAME="Cortex Linux"`
  - `packages/cortex-branding/debian/control`: package name, maintainer, homepage, VCS URLs all use "cortex"
  - `.github/workflows/build-iso.yml`: artifact names use "cortex-linux"
  - `.github/workflows/installation-tests.yml`: multiple "cortex" references in test assertions, repo config, grep patterns
- **Files:** ~10+ files across `src/`, `packages/`, `.github/workflows/`, `tests/`
- **Risk:** Medium — incorrect substitution could break build scripts or package dependencies. Requires careful surgical edits, not blind find-replace.

### #54: [CI] Automated ISO build and publish workflow
- **Complexity:** Medium
- **What to do:** The workflow `.github/workflows/build-iso.yml` already exists and handles most of this. Remaining work:
  - Add QEMU smoke test job
  - Verify release artifact naming matches CX branding
  - Ensure SBOM generation step is functional
- **Files:** `.github/workflows/build-iso.yml`
- **Risk:** Low — CI changes can be tested in PR without affecting main

### #59: Record demo GIFs for README
- **Complexity:** Low
- **What to do:** This is a content creation task. Agent can create placeholder entries in README with `asciinema` or `terminalizer` configuration files, but **cannot record actual terminal GIFs** without a running system.
- **Files:** `README.md`, potentially new `docs/demos/` directory
- **Risk:** None — additive content only
- **Note:** Partial completion — agent can scaffold the infrastructure but not produce actual recordings

### #46: Integrate Calamares graphical installer
- **Complexity:** High
- **What to do:** Create Calamares configuration module including:
  - `src/mods/XX-calamares-mod/install.sh` — install Calamares in chroot
  - Branding configuration files (JSON/YAML) for CX Linux
  - Module configuration (partition, locale, users, etc.)
  - Desktop `.desktop` file for installer icon
  - GRUB menu entries for live boot vs install
- **Files:** New mod directory + Calamares config files
- **Risk:** Medium — Calamares configuration is well-documented but requires careful module selection. Cannot test without a live ISO boot.

---

## YELLOW (Needs Clarification)

These issues have ambiguous requirements or missing context that prevents confident implementation.

### #55: Build and publish cx-core .deb package to apt repository
- **Question:** The `packages/cx-core/` directory already exists with `debian/control`. Is this issue about the meta-package that exists, or about packaging the `cx-cli` Python application (referenced in body as "cx-cli Python source")? These are fundamentally different tasks.
- **Also unclear:** What is the GPG key passphrase management strategy for CI? The workflow needs secrets configuration that we can't set up.

### #56: Build and publish cx-stacks .deb package
- **Question:** There is no `cx-stacks` source code in this repository. Where does the Python module live? Is it in a separate repo (`cxlinux-ai/cx-cli` or similar)? We cannot package code that doesn't exist here.
- **Blocked by:** Source code location unknown

### #57: Build and publish cx-ops .deb package
- **Question:** Same as #56 — no `cx-ops` source code in this repository. Where is the Python module? What are the health check specifications?
- **Blocked by:** Source code location unknown

### #58: Test apt install flow on Ubuntu 24.04
- **Question:** The test suite `tests/installation-tests.sh` already exists and covers these scenarios. Is this issue about:
  (a) Running the existing tests and fixing failures?
  (b) Creating new tests beyond what exists?
  (c) Setting up a Vagrant/QEMU VM for automated testing?
- **Also:** Testing requires a published APT repository with actual packages. Cannot test `apt install cx-core` without a live repo.

### #8: [1.8] Reproducible builds, artifact signing, and SBOM outputs
- **Question:** This is an epic with 13 decisions and 10 tasks. Which specific sub-tasks should be prioritized? Some components exist (SBOM generation in CI, GPG signing). What's the scope boundary for an agent contribution?

---

## RED (Blocked)

These issues cannot be completed by agents alone due to external dependencies, hardware requirements, or need for human architectural decisions.

### #1: [1.1] Automated installation and first-boot provisioning
- **Blocker:** Epic requiring architectural decisions on preseed vs cloud-init, first-boot wizard design, systemd service topology. Needs human product decisions on user experience.
- **Sub-tasks that COULD be GREEN:** Creating preseed template files, cloud-init config scaffolding

### #2: [1.2] Cortex package repository and apt trust model
- **Blocker:** Requires decisions on key rotation policy, offline mirror strategy, and pinning rules. Some infrastructure (reprepro, GPG signing) already exists. Needs human decisions on security policy.
- **Sub-tasks that COULD be GREEN:** Documenting current trust model, adding key rotation scripts

### #3: [1.3] Debian base selection and compatibility contract
- **Blocker:** Fundamental architectural decision — Debian stable vs testing, LTS commitment, architecture support. This is a product/business decision, not a code task.

### #4: [1.4] Debian packaging strategy for Cortex components
- **Blocker:** Epic requiring decisions on 18 packaging tasks across multiple services (CLI, LLM runtime, web console, privilege broker, agents). Most source code for these services doesn't exist in this repo.
- **Sub-tasks that COULD be GREEN:** Package template scaffolding, lintian configuration

### #5: [1.5] GPU driver enablement and packaging (NVIDIA/AMD)
- **Blocker:** Packages `cx-gpu-nvidia` and `cx-gpu-amd` exist as meta-packages, but testing requires actual GPU hardware. Decisions needed on DKMS vs prebuilt modules, Secure Boot/MOK signing strategy.
- **Sub-tasks that COULD be GREEN:** Improving package dependencies, adding detection scripts

### #6: [1.6] ISO image build system (live-build vs debian-installer)
- **Blocker:** Core architectural decision. Live-build is currently implemented but the epic calls for evaluation of alternatives. Needs human decision on installer strategy.
- **Sub-tasks that COULD be GREEN:** Documenting current live-build config, adding build validation

### #7: [1.7] Kernel, firmware, and hardware enablement plan
- **Blocker:** Requires hardware testing and decisions on supported hardware classes, kernel version strategy, Secure Boot enrollment. Cannot be automated.

### #9: [1.9] Upgrade, rollback, and version pinning
- **Blocker:** Requires decisions on rollback strategy (btrfs snapshots? apt pinning? custom tool?), preflight check design, and audit logging format. `src/upgrade.sh` exists but is minimal.

---

## Issues That Are Already PRs

The following "issues" are actually open Pull Requests. They should be reviewed/merged rather than re-implemented:

| Issue/PR | Title | Branch | Status |
|----------|-------|--------|--------|
| #60 | fix: Correct clone URL | `fix/correct-clone-url` | Open |
| #61 | docs: Add SPDX license identifier | `docs/spdx-license-identifier` | Open |
| #62 | fix: Unify domain references | `fix/unify-domain-references` | Open |
| #53 | Rebrand to CX Linux | `rebrand` | Draft |
| #51 | Add copilot-instructions.md | `copilot/add-copilot-instructions-file` | Draft |

**Recommendation:** Review these PRs first. If they are complete and correct, merge them. If not, the agent swarm can create fresh implementations.

---

## Recommended Execution Order

If GREEN list is approved, the recommended order (respecting dependencies) is:

1. **#53** — Rebrand to CX Linux (foundational — all other changes should be on top of correct branding)
2. **#60** — Fix clone URL (depends on #53 for consistent branding)
3. **#62** — Unify domain references (depends on #53)
4. **#61** — Add SPDX license identifier (independent, low risk)
5. **#51** — Add copilot-instructions.md (independent, documentation)
6. **#54** — Improve CI workflow (builds on correct branding from #53)
7. **#46** — Integrate Calamares installer (complex, independent)
8. **#59** — Demo GIF scaffolding (lowest priority, partial completion only)

---

## Awaiting Human Approval

**Please review the GREEN list above and confirm which issues the agent swarm should proceed with.** Specifically:

1. Should we create fresh implementations or review/improve the existing PRs for #60, #61, #62, #51, #53?
2. Is the recommended execution order acceptable?
3. Are there any YELLOW issues you can clarify to move them to GREEN?
4. Are there specific sub-tasks from RED epics you'd like extracted and queued?
