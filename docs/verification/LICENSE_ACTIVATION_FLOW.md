# License activation flow — Pro (Stripe “CX Core+”) customer path

Evidence from `cx-core` (this repo), shallow clone of `cx-web`, and live **read-only** calls to `https://license.cxlinux.com` (no Stripe charges, no checkout completion).

## Canonical activation command

**`cx activate <LICENSE_KEY>`**

Aliases (backward compatible): `cx-terminal activate …`, `cx license activate …`.

Site copy still to fix: `docs/verification/CX_WEB_COPY_TODO.md`.

## End-to-end flow (intended)

| Step | What the customer sees / does | Code / service | Verified |
|------|------------------------------|----------------|----------|
| 1 | Open [cxlinux.com/pricing](https://cxlinux.com/pricing), choose **Pro** ($20/mo) | `cx-web` pricing UI | PASS (prior e2e) |
| 2 | Checkout form → **Subscribe Now** → Stripe Hosted Checkout | `POST /api/stripe/checkout-session` on cx-web; license server also exposes Stripe checkout | PASS (redirect to `checkout.stripe.com`, product **CX Core+**) |
| 3 | Pay on Stripe (card) | Stripe live mode | **SKIP** (no payment in this run) |
| 4 | Redirect to success URL with `?session_id=cs_live_…` | `cx-web` `pricing/success.tsx` | Code reviewed |
| 5 | Success page polls license server for key | `GET https://license.cxlinux.com/api/v1/stripe/checkout-session/{sessionId}` every 2s, up to 5 tries | **PARTIAL** — invalid session returns `{"error":"No such checkout.session: …","valid":false}` (API reachable) |
| 6 | UI shows license key + copy button | `subscription.licenseKey` in success page | **UNVERIFIED** without real `session_id` |
| 7 | Email fallback if key slow | “sent to {email} within a minute” | **UNVERIFIED** |
| 8 | Account dashboard | [cxlinux.com/account](https://cxlinux.com/account) — `license.key`, `cx activate {key}` hint | Code in `cx-web/client/src/pages/account.tsx` |
| 9 | Install CX | APT instructions in README / getting-started | Ubuntu 24.04 PASS; Debian 12 FAIL (see INSTALL_VERIFICATION.md) |
| 10 | Activate on machine | `cx activate <KEY>` | **PASS** on Bookworm-built local `.deb` (invalid key); **FAIL** on published APT until release |
| 11 | Check status | `cx license` / `cx-terminal license` | Same as step 10 |
| 12 | Server validation | `POST /api/v1/licenses/activate` then `POST /api/v1/licenses/validate` with `hardware_id` | **PARTIAL** — invalid key returns `{"error":"Invalid license key","valid":false}` |

## License server (live probes, 2026-10-19)

**Health**

```bash
curl -sS https://license.cxlinux.com/health
```

```json
{"status":"ok","service":"CX Linux License Server","version":"2.0.0","features":["licensing","referrals","referral-tiers","2nd-level-commissions","stripe-checkout","stripe-webhooks","otp-verification","audit-logs","user-dashboard"],…}
```

**Validate (invalid key)**

```bash
curl -sS -X POST https://license.cxlinux.com/api/v1/licenses/validate \
  -H 'Content-Type: application/json' \
  -d '{"license_key":"CX-PRO-TEST-TEST-TEST-TEST","hardware_id":"deadbeefdeadbeef"}'
```

→ `{"error":"Invalid license key","valid":false}`

**Activate (invalid key)**

```bash
curl -sS -X POST https://license.cxlinux.com/api/v1/licenses/activate \
  -H 'Content-Type: application/json' \
  -d '{"license_key":"CX-PRO-TEST-TEST-TEST-TEST","hardware_id":"deadbeefdeadbeef","device_name":"test","platform":"linux","hostname":"test"}'
```

→ `{"error":"Invalid license key","valid":false}`

## CLI implementation (`cx-core`)

- Module: `wezterm/src/cli/license.rs` — stores key in `~/.cx/license.key`, talks to `https://license.cxlinux.com`.
- Commands: `ActivateCommand`, `LicenseCommand` in `wezterm/src/cli/mod.rs`.
- Hardware ID: hash of hostname, `/etc/machine-id`, boot_id, `USER` (see `generate_hardware_id()`).

**This PR fixes:**

1. Top-level `cx-terminal activate` / `license` (were only under `cx-terminal cli …`).
2. `cli activate` no longer requires a running mux server before calling the license API.
3. Debian package postinst adds `update-alternatives` symlink `cx` → `cx-terminal`.

## Copy / UX inconsistencies (customer confusion)

| Location | Text |
|----------|------|
| `cx-web` success (one page) | `cx license activate {key}` |
| `cx-web` success (other) | `cx activate {key}` |
| `account.tsx` | `cx activate {key}` |
| `wezterm-gui` enforcement | `cx license activate <key>` |
| Published APT binary name | `cx-terminal` only (no `cx` until next deb) |

## Blockers for a real paying customer (priority)

1. **Cannot activate on current APT package** — no top-level `activate`/`license`; `cli activate` tried to spawn missing `wezterm-mux-server` (deb ships `cx-mux-server`). **Requires new release to repo.cxlinux.com** with this PR’s CLI + packaging fixes.
2. **Post-payment key delivery unverified** — need one completed checkout (or Stripe test-mode session with matching license-server config) to confirm polling returns `licenseKey`.
3. **Debian 12 users cannot install via APT** — glibc/openssl dependency mismatch.
4. **Naming** — marketing “Pro” vs Stripe “CX Core+”; docs use `cx` vs package `cx-terminal`.

## Unit test

`cargo test -p cx-terminal license::tests::test_hardware_id_generation` (deterministic hardware ID) — run in CI via existing `cx-test` where applicable.
