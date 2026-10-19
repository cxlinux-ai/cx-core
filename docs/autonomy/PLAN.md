# CX Linux — 7-day autonomy plan (first paying user)
**Window:** Mon 2026-10-19 → Mon 2026-10-26 (America/Denver)  
**Goal:** One confirmed paying user (Stripe live charge + license activated).  
**Evidence base:** `../e2e-test-2026-10-19.md` — pricing LIVE; Pro checkout reaches Stripe `cs_live_` (AIVH LLC, CX Core+ $20).

Owners: **cloud** = cloud coding agent · **linus** = this bot · **mike** = Michael-only.

## Ranked tasks (impact × dependency)

| ID | Day | Owner | Repo | Task | Done-test |
|---|---|---|---|---|---|
| T01 | D0–D1 (Oct 19–20) | **mike** | — | Complete or designate one **$20 Pro** live purchase; save receipt + license key | Stripe dashboard shows paid sub; license email or success page shows key; optional `cx license activate <key>` OK |
| T02 | D0 (Oct 19) | **linus** | — | File e2e + this plan; queue NEEDS_MIKE | Files exist under `org/vision/linus/` + `autonomy/` |
| T03 | D1 (Oct 20) | **cloud** | `cx-web` | SPA host rewrite: all app routes return **HTTP 200** with index.html (fix soft-404) | `curl -s -o /dev/null -w '%{http_code}' https://cxlinux.com/pricing` → **200** (after Mike deploys) |
| T04 | D1 (Oct 20) | **cloud** | `cx-web` | Align naming: site “Pro” ↔ Stripe “CX Core+” (copy + success page); document price IDs | PR: UI says one canonical name; checklist of `price_1SqYQj…` IDs in PR body |
| T05 | D1 (Oct 20) | **cloud** | `cx-web` | “Install in 60 seconds” CTA → `/getting-started` (not checkout?plan=core) | Playwright/click: button lands on getting-started; Core free path still clear |
| T06 | D2 (Oct 21) | **cloud** | `cx-web` / license worker | Harden checkout error UX when session create fails; add visible error toast | Force bad price id in staging **or** unit test; user sees message (no silent stay) |
| T07 | D2 (Oct 21) | **linus**+**mike** | — | Approve + send Suyash/Dhruv re-engage draft | Draft in `../drafts/`; Mike/Rally sends; reply logged in LOG |
| T08 | D2–D3 (Oct 21–22) | **cloud**/devs | — | Disposable Ubuntu 24.04 apt install from `repo.cxlinux.com` | Script/log: key install, apt update, `apt-get install -y cx-terminal`, `cx-terminal --version` |
| T09 | D3 (Oct 22) | **cloud**/devs | — | Same on Debian 12; document libc6≥2.39 risk | Pass or written FAIL with dependency note |
| T10 | D3 (Oct 22) | **linus** | — | After T01: verify license activate + `/account` login path | Screenshot/log of activated license; mark PASS in LOG |
| T11 | D4 (Oct 23) | **cloud** | `cx-core` | Triage open PRs: label merge/close/needs-rebase; no merge | PR comment draft list in `NEEDS_MIKE` (max 10) |
| T12 | D4 (Oct 23) | **cloud** | `cx-core` | README one-liner: commercial licensing live + install link | PR diff on README |
| T13 | D5 (Oct 24) | **linus** | — | First-user playbook: pricing URL → pay → activate → ask dry-run | `../drafts/first-user-playbook.md` |
| T14 | D5 (Oct 24) | **mike** | Stripe | Reactivate or archive inactive Cortex products; confirm Core+/Pro prices | Stripe product list shows intended CX SKUs active only |
| T15 | D6 (Oct 25) | **linus** | — | Scorecard: paying user? Y/N + blockers | `../scorecards/2026-10-25.md` |
| T16 | D7 (Oct 26) | **linus** | — | Week rollup for Dez; next-week ask | `status.md` + LOG append |

## Progress (updated 2026-10-19 09:30 MT)
- T02 DONE. T03/T04/T05 DONE as draft cx-web PR #57 (verified, awaiting Mike merge = M-PR57).
- T08 Ubuntu PASS / T09 Debian FAIL + T11 triage DONE in draft cx-core PR #774; Bookworm build in progress.
- T06 IN PROGRESS (cloud agent bc-71fb33cc, separate cx-web PR). T13 DRAFTED early (`../drafts/first-user-playbook.md`); launch posts drafted (`../drafts/launch-posts-DRAFT.md`).
- Critical path: M1 ($20 test) + M-CORE (merge #771→#772→#774, new APT release).

## Dependency graph (short)
T01 (first $) is **unblocked by engineering** today — e2e proved Stripe page loads.  
T03–T05 improve conversion/SEO but are **not** required before T01.  
T07–T09 validate install funnel after/in parallel with T01.  
T11–T12 rebuild trust post-revenue.

## Out of scope this week
New core features, llama.cpp rewrite, Ed Honour outreach (contact unconfirmed), promising pay/equity to devs, bot-to-bot polling.
