# Issue: Contribution Guidelines Reset

**Priority:** High
**Labels:** documentation, process
**Milestone:** v0.2.0 Identity Reset

## Summary

Establish clear, fair contribution guidelines that prevent payment disputes and set proper expectations.

## Problems to Solve

1. **Double-dipping:** Contributors on monthly retainer also billing bounties
2. **Unclear expectations:** "Full-time" without defined hours
3. **Access creep:** Contributors getting Admin access when Write is sufficient
4. **Payment delays:** Bounties not paid promptly, causing frustration

## New Contribution Tiers

### Tier 1: Bounty Hunters (Default)
- **Compensation:** Per-PR bounties only
- **Access:** Write (can create PRs, cannot merge)
- **Expectation:** No time commitment, paid per deliverable
- **Payment:** Within 7 days of PR merge

### Tier 2: Core Contributors
- **Compensation:** Monthly retainer ($X/month)
- **Access:** Write + code review duties
- **Expectation:** X hours/week minimum, all work included in retainer
- **Payment:** Monthly, no additional bounties

### Tier 3: Maintainers (@GidTeam)
- **Compensation:** Salary/equity
- **Access:** Admin on assigned repos
- **Expectation:** Full accountability for repo health
- **Payment:** Per employment agreement

## Access Levels by Role

| Role | cx-core | cx-commercial | cx-infrastructure |
|------|---------|---------------|-------------------|
| Bounty Hunter | Write | None | None |
| Core Contributor | Write | Read | None |
| Maintainer | Admin | Admin | Admin |

## New CONTRIBUTING.md Sections

### Payment Terms
- Bounties: Paid in BTC/USDC within 7 days of merge
- Retainers: Paid monthly, includes ALL work (no bounty stacking)
- Disputes: Escalate to @GidTeam within 48 hours

### Bounty Schedule
| Type | Amount |
|------|--------|
| Typo/Doc fix | $10-25 |
| Bug fix (minor) | $25-50 |
| Bug fix (critical) | $100-200 |
| Feature (small) | $50-100 |
| Feature (medium) | $200-500 |
| Feature (large) | $500-1000+ |

### Rules
1. Bounty amounts are set BEFORE work begins
2. PRs must pass CI and code review
3. No self-merging (requires 1 approval)
4. Retainer contributors cannot also claim bounties

## Acceptance Criteria

- [ ] CONTRIBUTING.md updated with clear tiers
- [ ] Payment terms documented
- [ ] Access levels match role definitions
- [ ] Existing contributors notified of changes
