# DECISIONS (CX Linux autonomous week, Oct 19–26 2026)
Format: date MT | decision | why | how to undo

- 2026-10-19 | Project = CX Linux; goal = first paying user (working install + Pro/Team checkout path + healthy repos), end Mon Oct 26 | Michael chose "Restart" Oct 19 and gave the autonomy mandate with blank placeholders | Michael edits this line
- 2026-10-19 | Canonical autonomy docs live on the box at /workspace/aivh/org/vision/linus/autonomy/ and get mirrored to docs/autonomy/ on a non-main branch PR in cxlinux-ai/cx-core | Pushing to main or merging is off-limits; a branch PR is reversible | close the PR / delete the branch
- 2026-10-19 | Merges stay queued for Michael (NEEDS_MIKE) even though the mandate doesn't list them | Linus's standing rule: no merges without Michael's tap | Michael grants merge authority
- 2026-10-19 | One daily cycle, weekdays ~9am MT | AIVH cost rules: at most one weekday routine | change the routine schedule
- 2026-10-19 | Pricing page classified LIVE; HTTP 404 = SEO-only soft-404, not a relaunch blocker | Michael browser screenshot + Playwright render | reclassify if host returns empty body
- 2026-10-19 | First-$ path = live Stripe Checkout (Pro/$20 → product name CX Core+ on Stripe hosted page); no new pricing design this week | e2e reached cs_live_ on checkout.stripe.com as AIVH LLC | change SKU/name via Stripe+cx-web PR
    10|- 2026-10-19 | Cloud agents may open PRs on cx-web/cx-core; merges remain Mike-queued unless M5 granted | standing Linus rule | grant M5

- 2026-10-19 | cx-web PR #57 renames site 'CX Pro' to 'CX Core+' to match live Stripe product (plan id stays pro) | copy-only, matches what buyers see at checkout, no Stripe write needed | revert the copy commit, or rename the Stripe product instead (checklist in PR #57)
- 2026-10-19 | Docs mirror on PR #773 updates only our 5 files; never removes others' files | 09:36 mistake removed two files | restore commit on #773
- 2026-10-20 | Reposition CX as 'safe AI operations layer for Debian/Ubuntu fleets' (dry-run default, sandboxed, audited, reversible, local-first, removable); buyer = server teams (Team/Enterprise); drop unverified deck claims (Sapiens 55%, $1B at $2.4M ARR, 19K clones/10K customers) | Michael's market read Oct 20 4:08am MT | revert to prior positioning
- 2026-10-20 | Docs mirror: #773 (docs/autonomy/) is merged to main, so each later sync is a new small docs-only branch PR in cx-core, never a direct push to main | keeps main untouched without a tap | close that PR
- 2026-10-20 | Routine runs can't reply to cloud agents started in other runs (tool limit), so follow-ups launch a fresh Composer 2.5 agent that works on the existing PR branch (cx-core #774) | avoids duplicate PRs | n/a
- 2026-10-20 | cx-web copy: canonical activation command is `cx activate <LICENSE_KEY>`; install/support copy claims only verified OS (Ubuntu 24.04 PASS; Debian 12 not yet) | matches FACTS.md + #774 evidence | revert the cx-web PR
- 2026-10-21 | Hold #775; fix the sandbox on its own branch (new cloud agent, no new PR) before recommending merge | independent review found installs fail under firejail/bwrap and bwrap discards writes; agent must reproduce first | close the agent's commits with a revert on the branch
- 2026-10-21 | New critical path: #776 → #774 → APT release → M1; #775 no longer gates #774 | both are conflict-free against main; #775 isn't needed for license activation | restore the Oct 20 order in NEEDS_MIKE
    20|- 2026-10-21 | Marketing drafts and FACTS.md treat Sandbox as FAIL for installs and never mention AppArmor | claims must match proof | update FACTS.md when the fix is verified
- 2026-10-21 | Michael's Claude track (docs/autonomy/claude/, #778/#779) is a parallel workstream: read its PRs as evidence, don't duplicate its work, don't edit its files | avoids conflicting edits | n/a
- 2026-10-22 | install.sh npm issue handled as a top NEEDS_MIKE tap, not an interrupt | live but old, 0 known paying users, Michael's own Claude track already opened the fix (#62) | wake Michael if a real user reports it
- 2026-10-22 | Suggest #780 merges before #775, then a Linus agent rebases #775 onto #780's parser | #780 proves execution with a real model; #775's gate only works with a mock | swap the order in NEEDS_MIKE
- 2026-10-22 | Weekly scorecard filed Fri Oct 23 instead of Sun Oct 25 | routine is weekday-only | file a Monday addendum
- 2026-10-23 | #781 (package guard) replaces #775's sudo-apt host bypass; after #780/#781 merge, re-scope #775 to dry-run default + sandbox for non-package commands | #781 previews with apt-get -s, runs without a shell and records undo; safer than an unsandboxed bypass | restore the Oct 22 order in NEEDS_MIKE
