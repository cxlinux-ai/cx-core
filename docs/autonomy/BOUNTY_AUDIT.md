# Bounty Ledger & Compliance Audit

**Run:** 2026-10-19 · **Source:** live `gh` data (issues, PRs, merges, assignees) for `cxlinux-ai/cx-core` and `cxlinux-ai/cx-distro`
**Policy checked (FR-003):** every bounty issue states an amount and the post-funding bonus (`Bounty: $XX (+ $XX bonus after funding)`); payment is owed on merge to `main`, never on assignment; first-come-first-served assignment (FR-004).

## 1. Payouts owed (merged, pay-on-merge triggered)

| Repo | PR | Contributor | Merged | Closes | Stated bounty | Bonus note on issue | Paid? | Contributor follow-up |
|---|---|---|---|---|---|---|---|---|
| cx-distro | [#76](https://github.com/cxlinux-ai/cx-distro/pull/76) | @silasbrookshaha | 2026-10-10 | [#26](https://github.com/cxlinux-ai/cx-distro/issues/26) | **$25** upon merge | No | No evidence of payment on the thread | Asked how to claim on 2026-10-11 — **unanswered 8 days** |
| cx-distro | [#83](https://github.com/cxlinux-ai/cx-distro/pull/83) | @Ravikirar | 2026-10-16 | [#34](https://github.com/cxlinux-ai/cx-distro/issues/34) | **$25** upon merge | No | No evidence of payment on the thread | None yet |

**Total currently owed: $50.** Both source issues had been closed in Nov 2025 "for MVP focus" while still advertising the bounty, and were completed anyway — the bounty terms on those issues stand.

Payment state cannot be confirmed from GitHub alone (tip.cc payments happen in Discord). The ledger above treats "no payment acknowledgement on the PR or issue" as unpaid.

## 2. Open bounty issues — compliance

### cx-core

| Issue | Amount | Bonus note | Assignee | Competing PR | Finding |
|---|---|---|---|---|---|
| [#425](https://github.com/cxlinux-ai/cx-core/issues/425) llama.cpp native inference | $150 | ✅ | @sujay-d07 | [#766](https://github.com/cxlinux-ai/cx-core/pull/766) by @Ishant5436 | **FCFS conflict** — PR from a non-assignee |
| [#428](https://github.com/cxlinux-ai/cx-core/issues/428) dependency conflict prediction | $150 | ✅ | @Suyashd999 | [#753](https://github.com/cxlinux-ai/cx-core/pull/753) by @lustsazeus-lab | **FCFS conflict** — PR from a non-assignee |

All other open cx-core issues carry no bounty (CLA-signature issues and unpriced feature issues #708, #709, #712, #723, #724, #726, #702, #424). Two of them already have PRs: #708 ← [#765](https://github.com/cxlinux-ai/cx-core/pull/765), #712 ← [#744](https://github.com/cxlinux-ai/cx-core/pull/744). If those are merged, the contributors will reasonably ask about payment — price them or label them `no-bounty` first.

### cx-distro

| Group | Issues | Bonus note | Finding |
|---|---|---|---|
| Compliant | #22 ($75), #23 ($100), #24 ($100), #25 ($75, worded "+ $75 at funding"), #47 ($25), #50 (as stated on issue) | ✅ | OK |
| **Non-compliant — amount but no bonus note** | #27, #28, #29, #30, #31, #32, #33, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #48 (all $25) | ❌ | **19 issues** violate the template. Adding the note creates a post-funding commitment of the same amounts (**+$475** total) — queued for Mike, not edited autonomously |

### FCFS conflicts in cx-distro

| Issue | Assignee | PR | PR author |
|---|---|---|---|
| [#45](https://github.com/cxlinux-ai/cx-distro/issues/45) Package Conflict Resolution UI | @Sahilbhatane (since 2026-01-20) | [#72](https://github.com/cxlinux-ai/cx-distro/pull/72) | @dnesdan |
| [#50](https://github.com/cxlinux-ai/cx-distro/issues/50) Dependency Conflict Resolver | @Sahilbhatane (since 2026-01-21) | [#75](https://github.com/cxlinux-ai/cx-distro/pull/75) | @jienigoto |
| [#24](https://github.com/cxlinux-ai/cx-distro/issues/24) Safe NVIDIA installer | unassigned | [#71](https://github.com/cxlinux-ai/cx-distro/pull/71) | @businesscurry123 — **clean FCFS** |

@Sahilbhatane holds 3 cx-distro bounty assignments (#23, #45, #50) dated January with no linked PR from them; three outside contributors have since submitted work against two of them. That is the pattern FR-004 exists to catch: assignments are stale and newcomers are delivering.

## 3. Budget exposure (pre-funding / post-funding)

| Bucket | Pre-funding | Post-funding bonus |
|---|---|---|
| Owed now (#76, #83) | $50 | $50 if the bonus is honored on these two (not stated on their issues) |
| Open cx-core bounties (#425, #428) | $300 | $300 |
| Open cx-distro bounties with note | $325+ | $325+ |
| Open cx-distro bounties without note | $475 | $0 today → $475 if notes are added |

## 4. Process gaps found

1. No bounty ledger exists anywhere in the org — payouts are tracked only in contributor comments. This file is now the ledger; it should move to a pinned issue or a `BOUNTIES.md` the team maintains.
2. Closing an issue does not retire its bounty; closed-but-priced issues were picked up and merged (#26, #34).
3. Maintainer merges (#76, #83) happened without a payment step; there is no merge checklist tying "merged" to "paid".
