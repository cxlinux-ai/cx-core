# Zero Config API Keys

**Module:** `cortex/api_key_detector.py`

## Overview

Cortex automatically finds API keys from common locations without requiring users to manually set environment variables. This "zero config" approach means you can start using Cortex immediately if you already have API keys saved from other tools like the Claude CLI or OpenAI CLI.

```bash
$ cortex install nginx

🔑 Found ANTHROPIC API key in ~/.config/anthropic/credentials.json
📦 Installing nginx...
```

## Features

- **Auto-detection** from 5 common locations
- **Caching** to avoid repeated file checks
- **Smart save prompts** - only for file-based keys, not environment variables
- **Provider selection** when no key is found
- **Secure storage** with proper file permissions (600)

## Detection Locations

Cortex checks these locations in order of priority:

| Priority | Location | Description |
|----------|----------|-------------|
| 1 | Environment variables | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` *(used immediately, no save prompt)* |
| 2 | `~/.cortex/.env` | Cortex's own config directory |
| 3 | `~/.config/anthropic/credentials.json` | Claude CLI location |
| 4 | `~/.config/openai/credentials.json` | OpenAI CLI location |
| 5 | `.env` in current directory | Project-local environment file |

### File Format Support

The detector supports multiple file formats:

**JSON format** (Claude/OpenAI CLI style):
```json
{"api_key": "sk-ant-api03-..."}
```

**Environment format** (.env style):
```bash
ANTHROPIC_API_KEY=sk-ant-api03-...
```

**Raw key** (single line):
```
sk-ant-api03-...
```

## Usage

### Automatic Detection

Simply run any Cortex command. If a key is found outside the default location, you'll be prompted to save it:

```bash
$ cortex install nginx --dry-run

🔑 Found ANTHROPIC API key in ~/.config/anthropic/credentials.json
API key found at following location
/home/user/.config/anthropic/credentials.json

Save to ~/.cortex/.env? [Y/n] y
✓ Key saved to ~/.cortex/.env
```

**Environment variables are used immediately without prompting**, as they are already properly configured:

```bash
$ export ANTHROPIC_API_KEY=sk-ant-api03-...
$ cortex install nginx --dry-run

📦 Planning installation...
```

On subsequent runs, Cortex uses the cached location silently:

```bash
$ cortex install nginx --dry-run

📦 Planning installation...
```

### No Key Found - Provider Selection

If no API key is found, Cortex prompts you to select a provider:

```bash
$ cortex install nginx

⚠️  No API key found. Select a provider:
  1. Claude (Anthropic)
  2. OpenAI
  3. Ollama (local, no key needed)

Enter choice [1/2/3]: 1
Enter your Anthropic API key (starts with 'sk-ant-'):
> sk-ant-api03-...

Save to ~/.cortex/.env? [Y/n] y
✓ Key saved to ~/.cortex/.env
```

### Ollama (No API Key Required)

For local, free inference without an API key:

```bash
$ cortex install nginx

⚠️  No API key found. Select a provider:
  1. Claude (Anthropic)
  2. OpenAI
  3. Ollama (local, no key needed)

Enter choice [1/2/3]: 3
✓ Using Ollama (local mode)
```

Or set the provider explicitly:

```bash
export CORTEX_PROVIDER=ollama
cortex install nginx
```

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic/Claude API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `CORTEX_PROVIDER` | Force provider: `claude`, `openai`, `ollama`, `fake` |

### File Locations

| File | Purpose |
|------|---------|
| `~/.cortex/.env` | Saved API keys (secure, 600 permissions) |
| `~/.cortex/.api_key_cache` | Cached key location for fast lookup |

### Cache Format

The cache file stores metadata about the last detected key:

```json
{
  "provider": "anthropic",
  "source": "/home/user/.cortex/.env",
  "key_hint": "sk-ant-api..."
}
```

## Security

### File Permissions

All sensitive files are created with mode `600` (user read/write only):

- `~/.cortex/.env` - API keys
- `~/.cortex/.api_key_cache` - Cache metadata

### Key Validation

API keys are validated by prefix pattern:

| Prefix | Provider |
|--------|----------|
| `sk-ant-` | Anthropic/Claude |
| `sk-` | OpenAI |

### No Key Logging

API keys are never logged in full. Only hints like `sk-ant-api...` appear in cache files.

## Troubleshooting

### Key Not Being Detected

1. **Check file permissions:**
   ```bash
   ls -la ~/.config/anthropic/credentials.json
   # Should be readable by your user
   ```

2. **Verify file format:**
   ```bash
   cat ~/.config/anthropic/credentials.json
   # Should be valid JSON: {"api_key": "sk-ant-..."}
   ```

3. **Clear cache and retry:**
   ```bash
   rm ~/.cortex/.api_key_cache
   cortex install nginx --dry-run
   ```

### Wrong Provider Selected

If Cortex selects the wrong provider:

```bash
# Force a specific provider
export CORTEX_PROVIDER=claude
cortex install nginx
```

### Save Prompt Keeps Appearing

If prompted to save repeatedly:

1. **Check if save succeeded:**
   ```bash
   cat ~/.cortex/.env
   # Should contain ANTHROPIC_API_KEY=sk-ant-...
   ```

2. **Check cache points to correct location:**
   ```bash
   cat ~/.cortex/.api_key_cache
   # "source" should be "/home/user/.cortex/.env"
   ```

3. **Check file permissions:**
   ```bash
   ls -la ~/.cortex/.env
   # Should be -rw------- (600)
   ```

### API Key Invalid Errors

If you get authentication errors:

1. **Verify key is complete** (no truncation or line breaks):
   ```bash
   cat ~/.cortex/.env | wc -c
   # Anthropic keys are ~100+ characters
   ```

2. **Test key directly:**
   ```bash
   curl https://api.anthropic.com/v1/messages \
     -H "x-api-key: $(grep ANTHROPIC ~/.cortex/.env | cut -d= -f2)" \
     -H "content-type: application/json" \
     -d '{"model":"claude-3-haiku-20240307","max_tokens":10,"messages":[{"role":"user","content":"Hi"}]}'
   ```

## Integration with Other Cortex Features

### First-Run Wizard

The first-run wizard (`cortex setup`) uses the API key detector internally. See [FIRST_RUN_WIZARD.md](FIRST_RUN_WIZARD.md).

### Environment Management

API keys can also be managed via `cortex env`. See [ENV_MANAGEMENT.md](ENV_MANAGEMENT.md).

### Configuration Export

When exporting configuration with `cortex config export`, API keys are **not** included by default for security.

## Testing

Run the API key detector tests:

```bash
pytest tests/test_api_key_detector.py -v
```

Test coverage includes:
- Detection from all 5 locations
- Priority ordering
- JSON and .env file parsing
- Cache creation and retrieval
- Save functionality
- User prompts
