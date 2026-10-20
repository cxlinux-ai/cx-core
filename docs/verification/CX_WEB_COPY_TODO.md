# cx-web copy to align with canonical `cx activate <LICENSE_KEY>`

Canonical activation command (cx-core): **`cx activate <LICENSE_KEY>`**

Backward-compatible aliases (no cx-web change required): `cx-terminal activate …`, `cx license activate …`

| File | Current copy | Change to |
|------|----------------|-----------|
| `client/src/pages/pricing/success.tsx` | `cx license activate {subscription.licenseKey}` | `cx activate {subscription.licenseKey}` |
| `client/src/pages/account.tsx` | `cx activate ${license.key}` (clipboard hint) | **Already canonical** |
| `client/src/pages/pricing-success.tsx` | `cx activate ${sessionData?.licenseKey}` | **Already canonical** |

Optional consistency (mentions only):

- `getting-started` / install docs on site should prefer `cx` (symlink) over `cx-terminal` where both work.
