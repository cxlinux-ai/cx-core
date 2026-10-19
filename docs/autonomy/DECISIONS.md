# DECISIONS (CX Linux autonomous week, Oct 19–26 2026)
Format: date MT | decision | why | how to undo

- 2026-10-19 | Project = CX Linux; goal = first paying user (working install + Pro/Team checkout path + healthy repos), end Mon Oct 26 | Michael chose "Restart" Oct 19 and gave the autonomy mandate with blank placeholders | Michael edits this line
- 2026-10-19 | Canonical autonomy docs live on the box at /workspace/aivh/org/vision/linus/autonomy/ and get mirrored to docs/autonomy/ on a non-main branch PR in cxlinux-ai/cx-core | Pushing to main or merging is off-limits; a branch PR is reversible | close the PR / delete the branch
- 2026-10-19 | Merges stay queued for Michael (NEEDS_MIKE) even though the mandate doesn't list them | Linus's standing rule: no merges without Michael's tap | Michael grants merge authority
- 2026-10-19 | One daily cycle, weekdays ~9am MT | AIVH cost rules: at most one weekday routine | change the routine schedule
- 2026-10-19 | Pricing page classified LIVE; HTTP 404 = SEO-only soft-404, not a relaunch blocker | Michael browser screenshot + Playwright render | reclassify if host returns empty body
- 2026-10-19 | First-$ path = live Stripe Checkout (Pro/$20 → product name CX Core+ on Stripe hosted page); no new pricing design this week | e2e reached cs_live_ on checkout.stripe.com as AIVH LLC | change SKU/name via Stripe+cx-web PR
- 2026-10-19 | Cloud agents may open PRs on cx-web/cx-core; merges remain Mike-queued unless M5 granted | standing Linus rule | grant M5

- 2026-10-19 | cx-web PR #57 renames site 'CX Pro' to 'CX Core+' to match live Stripe product (plan id stays pro) | copy-only, matches what buyers see at checkout, no Stripe write needed | revert the copy commit, or rename the Stripe product instead (checklist in PR #57)
