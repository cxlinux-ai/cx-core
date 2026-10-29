# CX Linux — 7-day autonomy plan (first paying user)
**Window:** Mon 2026-10-19 → Mon 2026-10-26 (America/Denver)  
**Goal:** One confirmed paying user (Stripe live charge + license activated).  
**Evidence base:** `../e2e-test-2026-10-19.md` — pricing LIVE; Pro checkout reaches Stripe `cs_live_` (AIVH LLC, CX Core+ $20).

Owners: **cloud** = cloud coding agent · **linus** = this bot · **mike** = Michael-only.

## Ranked tasks (impact × dependency)

    10|| ID | Day | Owner | Repo | Task | Done-test |
|---|---|---|---|---|---|
| T01 | D0–D1 (Oct 19–20) | **mike** | — | Complete or designate one **$20 Pro** live purchase; save receipt + license key | Stripe dashboard shows paid sub; license email or success page shows key; optional `cx license activate <key>` OK |
| T02 | D0 (Oct 19) | **linus** | — | File e2e + this plan; queue NEEDS_MIKE | Files exist under `org/vision/linus/` + `autonomy/` |
| T03 | D1 (Oct 20) | **cloud** | `cx-web` | SPA host rewrite: all app routes return **HTTP 200** with index.html (fix soft-404) | `curl -s -o /dev/null -w '%{http_code}' https://cxlinux.com/pricing` → **200** (after Mike deploys) |
| T04 | D1 (Oct 20) | **cloud** | `cx-web` | Align naming: site "Pro" ↔ Stripe "CX Core+" (copy + success page); document price IDs | PR: UI says one canonical name; checklist of `price_1SqYQj…` IDs in PR body |
| T05 | D1 (Oct 20) | **cloud** | `cx-web` | "Install in 60 seconds" CTA → `/getting-started` (not checkout?plan=core) | Playwright/click: button lands on getting-started; Core free path still clear |
| T06 | D2 (Oct 21) | **cloud** | `cx-web` / license worker | Harden checkout error UX when session create fails; add visible error toast | Force bad price id in staging **or** unit test; user sees message (no silent stay) |
| T07 | D2 (Oct 21) | **linus**+**mike** | — | Approve + send Suyash/Dhruv re-engage draft | Draft in `../drafts/`; Mike/Rally sends; reply logged in LOG |
| T08 | D2–D3 (Oct 21–22) | **cloud**/devs | — | Disposable Ubuntu 24.04 apt install from `repo.cxlinux.com` | Script/log: key install, apt update, `apt-get install -y cx-terminal`, `cx-terminal --version` |
    20|| T09 | D3 (Oct 22) | **cloud**/devs | — | Same on Debian 12; document libc6≥2.39 risk | Pass or written FAIL with dependency note |
| T10 | D3 (Oct 22) | **linus** | — | After T01: verify license activate + `/account` login path | Screenshot/log of activated license; mark PASS in LOG |
| T11 | D4 (Oct 23) | **cloud** | `cx-core` | Triage open PRs: label merge/close/needs-rebase; no merge | PR comment draft list in `NEEDS_MIKE` (max 10) |
| T12 | D4 (Oct 23) | **cloud** | `cx-core` | README one-liner: commercial licensing live + install link | PR diff on README |
| T13 | D5 (Oct 24) | **linus** | — | First-user playbook: pricing URL → pay → activate → ask dry-run | `../drafts/first-user-playbook.md` |
| T14 | D5 (Oct 24) | **mike** | Stripe | Reactivate or archive inactive Cortex products; confirm Core+/Pro prices | Stripe product list shows intended CX SKUs active only |
| T15 | D6 (Oct 25) | **linus** | — | Scorecard: paying user? Y/N + blockers | `../scorecards/2026-10-25.md` |
| T16 | D7 (Oct 26) | **linus** | — | Week rollup for Dez; next-week ask | `status.md` + LOG append |

## Progress (updated 2026-10-19 09:30 MT)
    30|- T02 DONE. T03/T04/T05 DONE as draft cx-web PR #57 (verified, awaiting Mike merge = M-PR57).
- T08 Ubuntu PASS / T09 Debian FAIL + T11 triage DONE in draft cx-core PR #774; Bookworm build in progress.
- T06 IN PROGRESS (cloud agent bc-71fb33cc, separate cx-web PR). T13 DRAFTED early (`../drafts/first-user-playbook.md`); launch posts drafted (`../drafts/launch-posts-DRAFT.md`).
- Critical path: M1 ($20 test) + M-CORE (merge #771→#772→#774, new APT release).

## Progress (updated 2026-10-20 09:15 MT)
- T03/T04/T05 DONE + LIVE: cx-web #57 merged ~8:53am MT; https://cxlinux.com/pricing returns 200, junk path 404, sitemap 200 (curl 9:14am MT). T06 DONE + LIVE: #58 merged ~8:52am MT.
- cx-core #771 + #772 merged Oct 19. #773 docs mirror merged. #774 (license CLI, Bookworm CLI deb, apt smoke) now conflicts with main: rebase agent launched this cycle.
- New (repositioning): #775 dry-run default + safety demo (CI blocked only by pre-existing failures) and #776 CI unblock (green except CodeQL). Merge order: #776 → #775 → #774 → APT release → M1.
- Found on live site: activation copy mixes `cx activate` and `cx license activate`; install.sh claims Debian 11+ (Debian 12 fails). cx-web copy fix agent launched this cycle.
    40|- Next: T08/T09 rerun after #774 rebase; T10 after APT release + M1; T12 README line after #774/#775.

## Dependency graph (short)
T01 (first $) is **unblocked by engineering** today — e2e proved Stripe page loads.  
T03–T05 improve conversion/SEO but are **not** required before T01.  
T07–T09 validate install funnel after/in parallel with T01.  
T11–T12 rebuild trust post-revenue.

## Out of scope this week
New core features, llama.cpp rewrite, Ed Honour outreach (contact unconfirmed), promising pay/equity to devs, bot-to-bot polling.
    50|
## Progress (updated 2026-10-21 09:15 MT)
- Live site healthy; cx-web #61 (homepage SEO/HSTS) merged overnight by Michael's account. #60 clean and ready.
- cx-core #776 now fully green (incl. CodeQL via #778). Critical path re-ordered: #776 → #774 → APT release → M1 (T01) → T10.
- #775 on hold: sandbox fixes in progress (cloud agent bc-7d5d09f5). Marketing "sandboxed" claim downgraded until verified.
- T07 (dev re-engage send) still waiting on Michael. T11 done earlier; T12 README line after #774. T13 drafted. T15 scorecard due Oct 25.

## Progress (updated 2026-10-22 09:15 MT)
- No merges since Oct 21. Critical path unchanged: #776 → #774 → APT release → M1 → T10.
- #775 CI green on its fix commit except the 3 old failures; still HOLD (host-bypass review + #780 overlap). New suggested order on the AI side: #780 before #775, then rebase #775.
    60|- New live issue: install.sh installs an unrelated npm package on macOS/non-Debian; fix is cx-web #62 (into #60). Raised to tap #2.
- T15 scorecard moves to Fri Oct 23 (Oct 25 is a Sunday). T12 README still waits on #774.

## Progress (updated 2026-10-23 09:15 MT)
- No merges since Oct 21 (GitHub search 9:05 MT). Critical path unchanged: #776 → #62/#60 → #774 + APT release → M1 → T10.
- T15 DONE early: `../scorecards/2026-10-23.md` (paying user: NO).
- New from Michael's Claude track: cx-core #781 package guard (apt-get -s preview, [y/N] default No, audit + undo), stacked on #780. It covers #775's package-install path more safely. Suggested AI-side order: #780 → #781 → re-scope/rebase #775.
- #777 docs mirror verified: exactly the 5 autonomy files.
- Next: Mon Oct 26 wrap-up (T16). T12 README still waits on #774.

    70|## Progress (updated 2026-10-26 09:10 MT, last day)
- T16 DONE (status.md rollup). T15 filed early Oct 23. T01/M1, T10, T14 still Michael-only and not done.
- Critical path unchanged since Oct 21: #776 → cx-web #62/#60 → #774 + APT release → M1 $20 buy. Then #780 → #781 → re-scope #775.
- Low-risk extras from Claude track: cx-core #782 (README truth), cx-distro #84 (link fix). cx-web #63 merged Oct 25.
