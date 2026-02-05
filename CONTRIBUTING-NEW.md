# Contributing to CX Linux

Thank you for your interest in contributing to CX Linux! This document outlines how to contribute and our compensation structure.

## Code of Conduct

Be respectful, professional, and constructive. We're building something great together.

---

## Contribution Tiers

### Tier 1: Bounty Contributors (Default)

**Who:** Anyone who wants to contribute on a per-PR basis.

| Aspect | Details |
|--------|---------|
| **Compensation** | Per-PR bounties (see schedule below) |
| **Access** | Write (can create PRs, cannot merge) |
| **Expectation** | No time commitment |
| **Payment** | Within 7 days of PR merge |

### Tier 2: Core Contributors

**Who:** Invited contributors with ongoing involvement.

| Aspect | Details |
|--------|---------|
| **Compensation** | Monthly retainer (negotiated) |
| **Access** | Write + code review duties |
| **Expectation** | Agreed hours/week, all work included |
| **Payment** | Monthly, NO additional bounties |

> **Important:** Core contributors on a monthly retainer cannot also claim bounties. All work is included in the retainer.

### Tier 3: Maintainers (@GidTeam)

**Who:** Project leadership with full accountability.

| Aspect | Details |
|--------|---------|
| **Compensation** | Salary/equity |
| **Access** | Admin on assigned repositories |
| **Expectation** | Full ownership of repo health |

---

## Bounty Schedule

Bounties are assigned BEFORE work begins. Check the issue labels or ask in Discord.

| Type | Amount (USD) |
|------|--------------|
| Typo / Doc fix | $10 - $25 |
| Bug fix (minor) | $25 - $50 |
| Bug fix (critical/security) | $100 - $200 |
| Feature (small) | $50 - $100 |
| Feature (medium) | $200 - $500 |
| Feature (large) | $500 - $1,000+ |

### Bounty Rules

1. **Pre-approved amounts:** Bounty value is set on the issue before you start
2. **One PR per bounty:** Don't combine multiple bounties into one PR
3. **CI must pass:** PRs with failing tests won't be merged
4. **Code review required:** All PRs need at least 1 approval
5. **No self-merging:** You cannot approve your own PR
6. **Payment in 7 days:** Bounties paid within 7 days of merge

### Payment Methods

- BTC (preferred)
- USDC
- PayPal (on request)

---

## Repository Access

| Role | cx-core | cx-commercial | cx-infrastructure | cx-distro |
|------|---------|---------------|-------------------|-----------|
| Bounty Contributor | Write | None | None | Write |
| Core Contributor | Write | Read | None | Write |
| Maintainer | Admin | Admin | Admin | Admin |

**Access is granted based on role, not request.** Elevated access requires demonstrated trust and ongoing contribution.

---

## How to Contribute

### 1. Find an Issue

- Browse [open issues](https://github.com/cxlinux-ai/cx-core/issues)
- Look for `bounty` or `good first issue` labels
- Comment to claim an issue before starting

### 2. Fork and Branch

```bash
git clone https://github.com/YOUR-USERNAME/cx-core.git
cd cx-core
git checkout -b feature/your-feature-name
```

### 3. Make Changes

- Follow existing code style
- Add tests for new functionality
- Update documentation if needed

### 4. Submit PR

```bash
git push origin feature/your-feature-name
```

Then open a Pull Request with:
- Clear title (e.g., `fix: resolve nginx config parsing error`)
- Description of changes
- Link to related issue
- Screenshots/video if UI changes

### 5. Code Review

- Address reviewer feedback
- Keep PRs focused and small
- Be patient - reviews may take 24-48 hours

### 6. Get Paid

After merge:
1. Comment on the PR with your payment details (BTC address, etc.)
2. Payment sent within 7 days
3. Celebrate!

---

## Commit Message Format

```
type: short description

Longer description if needed.

Fixes #123
```

**Types:**
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation only
- `refactor:` Code change that neither fixes a bug nor adds a feature
- `test:` Adding tests
- `chore:` Maintenance tasks

---

## Questions?

- **Discord:** [discord.gg/cxlinux](https://discord.gg/cxlinux)
- **Email:** contributors@cxlinux.com

---

## Dispute Resolution

If you have concerns about payment, access, or contribution credit:

1. Raise the issue in Discord #contributors channel
2. Tag @GidTeam for escalation
3. Disputes must be raised within 48 hours of the event

We're committed to fair treatment of all contributors.

---

Thank you for helping build the AI Layer for Linux!
