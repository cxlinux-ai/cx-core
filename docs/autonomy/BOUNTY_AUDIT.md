# Bounty Ledger & Compliance Audit

**Run:** 2026-10-19 · **Source:** live `gh` data (issues, PRs, merges, assignees) for `cxlinux-ai/cx-core` and `cxlinux-ai/cx-distro`
**Policy checked (FR-003):** every bounty issue states an amount and the post-funding bonus (`Bounty: $XX (+ $XX bonus after funding)`); payment is owed on merge to `main`, never on assignment; first-come-first-served assignment (FR-004).

## Refresh — 2026-10-23 (live `gh` data, both repos)

**Nothing has changed since the 2026-10-19 run.** No bounty PR was merged, closed or updated; no payment acknowledgement appeared; no issue body was edited.

| Check | 2026-10-19 | 2026-10-23 |
|---|---|---|
| Owed on merge (cx-distro #76, #83) | $50 | **$50, still unpaid on-thread.** @silasbrookshaha's claim question on #76 (2026-10-11) is now **12 days** unanswered |
| Open cx-distro bounty issues missing the bonus note | 19 | 19 (#27–#33, #35–#45, #48; $25 each → +$475 if added) |
| FCFS conflicts | cx-core #425, #428; cx-distro #45, #50 | unchanged; @Sahilbhatane still holds #23, #45, #50 with no PR |
| New | — | **cx-distro #34:** @mimienco asked on 2026-09-13 whether the $25 task was available and payable via PayPal. The question was never answered, and #83 by another contributor later completed it. Same trust risk as #76 |
| Public issue text with the legacy brand | not counted | **34 of 40** open cx-distro issues (epics #1–#9 and all bounty issues) and cx-core #424, #425, #428. Public issue text is company communication, so editing it is queued for Mike (NEEDS_MIKE N30) |

Bounty tiers in issue text: $25 / $75 / $88 (#50) / $100 / $150. They match the recorded tiers except #50's $88, which is stated on the issue and stands as written.

## Corrections — 2026-10-25 (independent verification pass)
- #45 assignment date is 2025-12-04 (first assigned 2025-11-17, removed 2025-11-18); #50 is 2026-01-03. Earlier text said January 20/21.
- Open cx-distro bounties carrying the bonus note total **$463**, not "$325+".
- **Missed FCFS conflict:** cx-distro **#25** ($75 + $75 bonus, unassigned) has two competing PRs, both in cx-core: [#763](https://github.com/cxlinux-ai/cx-core/pull/763) (@KingParmenides, 2026-05-11, first) and [#764](https://github.com/cxlinux-ai/cx-core/pull/764) (@wangxq-cc, 2026-05-13). Both bodies say "Addresses cxlinux-ai/cx-distro#25". By first-come-first-served, #763 has priority if it meets the #781 safety bar.
- #26 and #34 were reopened on 2025-12-20, so they were open when completed.

## 1. Payouts owed (merged, pay-on-merge triggered)

| Repo | PR | Contributor | Merged | Closes | Stated bounty | Bonus note on issue | Paid? | Contributor follow-up |
|---|---|---|---|---|---|---|---|---|
| cx-distro | [#76](https://github.com/cxlinux-ai/cx-distro/pull/76) | @silasbrookshaha | 2026-10-10 | [#26](https://github.com/cxlinux-ai/cx-distro/issues/26) | **$25** upon merge | No | No evidence of payment on the thread | Asked how to claim on 2026-10-11 — **unanswered 8 days** |
| cx-distro | [#83](https://github.com/cxlinux-ai/cx-distro/pull/83) | @Ravikirar | 2026-10-16 | [#34](https://github.com/cxlinux-ai/cx-distro/issues/34) | **$25** upon merge | No | No evidence of payment on the thread | None yet |

**Total currently owed: $50.** Both source issues were closed in Nov 2025 "for MVP focus" and reopened on 2025-12-20, so they were open when the work was submitted and merged — the bounty terms on those issues stand.

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
| [#45](https://github.com/cxlinux-ai/cx-distro/issues/45) Package Conflict Resolution UI | @Sahilbhatane (since 2025-12-04) | [#72](https://github.com/cxlinux-ai/cx-distro/pull/72) | @dnesdan |
| [#50](https://github.com/cxlinux-ai/cx-distro/issues/50) Dependency Conflict Resolver | @Sahilbhatane (since 2026-01-03) | [#75](https://github.com/cxlinux-ai/cx-distro/pull/75) | @jienigoto |
| [#24](https://github.com/cxlinux-ai/cx-distro/issues/24) Safe NVIDIA installer | unassigned | [#71](https://github.com/cxlinux-ai/cx-distro/pull/71) | @businesscurry123 — **clean FCFS** |

@Sahilbhatane holds 3 cx-distro bounty assignments (#23, #45, #50) (assigned 2025-12-04 to 2026-01-03) with no linked PR from them, although #45's timeline shows commit references by them from Nov 2025 to Jan 2026. Two outside contributors have open PRs against two of them (#72 → #45, #75 → #50); closed PRs by a deleted account also targeted #23 and #50.

## 3. Budget exposure (pre-funding / post-funding)

| Bucket | Pre-funding | Post-funding bonus |
|---|---|---|
| Owed now (#76, #83) | $50 | $50 if the bonus is honored on these two (not stated on their issues) |
| Open cx-core bounties (#425, #428) | $300 | $300 |
| Open cx-distro bounties with note (#22 $75, #23 $100, #24 $100, #25 $75, #47 $25, #50 $88) | $463 | $463 |
| Open cx-distro bounties without note | $475 | $0 today → $475 if notes are added |

## 4. Process gaps found

1. No bounty ledger exists anywhere in the org — payouts are tracked only in contributor comments. This file is now the ledger; it should move to a pinned issue or a `BOUNTIES.md` the team maintains.
2. Issues closed "for MVP focus" and later reopened (#26, #34) kept their advertised bounties, which were then earned on merge.
3. Maintainer merges (#76, #83) happened without a payment step; there is no merge checklist tying "merged" to "paid".
