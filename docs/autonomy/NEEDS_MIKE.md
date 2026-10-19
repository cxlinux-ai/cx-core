# NEEDS_MIKE (ready-to-approve, short)

## M1 — First paying user ($20 Pro) — **DO THIS FIRST**
- **What:** Complete checkout at https://cxlinux.com/pricing → **Start with Pro** → fill name/email → **Subscribe Now** → pay $20 on Stripe (AIVH LLC, live; product shows as **CX Core+**).
- **Why:** E2E already reached `checkout.stripe.com` `cs_live_…` without card entry. This is the remaining gate to “first paying user.”
- **Done:** Forward receipt + license key (or success-page screenshot) to Linus via Dez notes / this folder.
- **Undo:** Stripe cancel/refund within 7-day money-back copy on page.

## M2 — Deploy SPA soft-404 fix (after cloud PR)
- **What:** Approve/merge + deploy `cx-web` PR that makes https://cxlinux.com/pricing return **HTTP 200** (SEO).
- **Why:** Page already renders; crawlers/link previews see 404.
- **URL:** https://cxlinux.com/pricing

## M3 — Send dev re-engage (draft ready)
- **What:** Approve send of `../drafts/reengage-suyash-dhruv-2026-10-19.md` to suyash@mmivip.com + dhruv@aiventureholdings.com (via Rally/Michael — not Linus).
- **Why:** Need apt smoke on Ubuntu/Debian + PR triage capacity.

## M4 — Stripe catalog hygiene (optional same week)
- **What:** In Stripe (acct connected as AIVH LLC): leave working **CX Core+ $20** path; archive/reactivate old **Cortex*** products (`active:false` today) so dashboard isn’t confusing.
- **Why:** Search found Cortex Pro/Enterprise/Managed inactive; live checkout still sold “CX Core+”.
- **No Linus writes** — Mike only.

## M5 — Merge authority for week (optional)
- **What:** Allow Linus to merge **non-main** autonomy-doc PRs and/or approve specific `cx-web` PRs for T03–T05.
- **Default:** merges stay queued here per DECISIONS.md.

## M6 — Open PR batch (after T11 list)
- **What:** Merge/close aging `cx-core` PRs per triage list (to be attached).
- **URL:** https://github.com/cxlinux-ai/cx-core/pulls

- ~~M0~~ DONE 08:52 MT: grant Cursor's GitHub app access to the cxlinux-ai org (card sent in chat Oct 19). Recommendation: approve, all repos in cxlinux-ai.

- **M-PR57:** merge https://github.com/cxlinux-ai/cx-web/pull/57 (pricing pages return 200 status, free Install button goes to /getting-started, "Pro" renamed "CX Core+" to match Stripe). READY (verified 09:15 MT: assets/blog/rss/sitemap OK on preview, junk 404, Core+ and Team checkout reach checkout.stripe.com via license.cxlinux.com). Recommendation: approve. Merging likely auto-deploys cxlinux.com; rollback = revert PR. Mark ready-for-review before merge.

- **M-CORE (most important):** a buyer who pays $20 today can't activate a license, because the published package is missing the `activate` command (proof: https://github.com/cxlinux-ai/cx-core/pull/774). Recommendation, in order: merge https://github.com/cxlinux-ai/cx-core/pull/771 (fixes CI build) → https://github.com/cxlinux-ai/cx-core/pull/772 (safety fix) → https://github.com/cxlinux-ai/cx-core/pull/774 (license CLI + `cx` command + install smoke test), then approve publishing a new APT package (production release). Until then, pause pushing paid traffic.
- **M-DEPS:** 5 Dependabot Action bumps (#762 #761 #749 #748 #747) look routine. Recommendation: approve as a batch after #771 makes CI green.

- **M-PR58:** merge https://github.com/cxlinux-ai/cx-web/pull/58 after #57 (checkout failure now shows a banner with Retry + support link; fixes a blog post that was dropped from listings). Local check/test/build pass; Cloudflare CI pending at 09:27 MT. Recommendation: approve once CI is green (next cycle verifies). Diff is +1643 lines, mostly tests; next cycle confirms no lockfile churn.
