# Issue 268 — End-user testing guide (semantic cache + offline)

This guide covers only how to test the feature added for issue #268.

## Prereqs

- Python 3.10+
- Project installed in editable mode

```bash
python -m venv venv
. venv/bin/activate
pip install -e .
```

## Test 1: Warm the cache (online)

Run a request once with an API key configured.

```bash
export OPENAI_API_KEY=sk-...
# or
export ANTHROPIC_API_KEY=sk-ant-...

cortex install nginx --dry-run
```

Expected:
- It prints generated commands.
- This run should create/update the cache database.

## Test 2: Check cache stats

```bash
cortex cache stats
```

Expected:
- `Hits` is >= 0
- `Misses` is >= 0
- `Saved calls (approx)` increases when cached answers are used

## Test 3: Offline mode (cached-only)

Run the same request with offline mode enabled.

```bash
cortex --offline install nginx --dry-run
```

Expected:
- If the request was warmed in Test 1, it should still print commands.
- If the request was never cached, it should fail with an offline-cache-miss message.

## Test 4: Verify cache hit (repeat request)

Run the original request again to verify cache is working:

```bash
cortex install nginx --dry-run
cortex cache stats
```

Expected:
- The second run should be faster (no API call)
- `cache stats` should show `Hits: 1`

## Notes

- Cache location defaults to `/var/lib/cortex/cache.db` and falls back to `~/.cortex/cache.db` if permissions don't allow system paths.
- Cache size and similarity threshold can be tuned with:
  - `CORTEX_CACHE_MAX_ENTRIES` (default: 500)
  - `CORTEX_CACHE_SIMILARITY_THRESHOLD` (default: 0.86)
- Cache is provider+model specific, so switching providers will cause a cache miss.
- The cache uses semantic similarity matching, so slightly different wording may still return cached results.
