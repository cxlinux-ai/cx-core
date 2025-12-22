# Environment Variable Management

Cortex provides first-class environment variable management with encryption, templates, validation, and seamless integration with your services.

## Overview

The `cortex env` command group allows you to:

- **Store** environment variables per application
- **Encrypt** sensitive values at rest
- **Template** common configurations (Node.js, Python, Django, etc.)
- **Validate** variable formats (URLs, ports, booleans, etc.)
- **Export/Import** environment files
- **Load** variables into running services

## Quick Start

```bash
# Set a simple variable
cortex env set myapp DATABASE_URL "postgres://localhost/db"
✓ Environment variable set

# Set an encrypted secret
cortex env set myapp API_KEY "secret123" --encrypt
🔐 Variable encrypted and stored

# List all variables for an app
cortex env list myapp
```

## Storage

### Location

Environment variables are stored in JSON files under:

```text
~/.cortex/environments/<app>.json
```

Each application has its own file, ensuring complete isolation between apps.

### File Format

```json
{
  "app": "myapp",
  "variables": [
    {
      "key": "DATABASE_URL",
      "value": "postgres://localhost/db",
      "encrypted": false,
      "description": "Database connection URL",
      "var_type": "url"
    },
    {
      "key": "API_KEY",
      "value": "gAAAAABk...encrypted_blob...",
      "encrypted": true,
      "description": "External API key",
      "var_type": "string"
    }
  ]
}
```

## Commands Reference

### Set a Variable

```bash
cortex env set <app> <KEY> <VALUE> [options]
```

**Options:**
- `--encrypt, -e` - Encrypt the value before storing
- `--type, -t` - Variable type for validation (string, url, port, boolean, integer, path)
- `--description, -d` - Description of the variable

**Examples:**

```bash
# Basic variable
cortex env set myapp NODE_ENV production

# Encrypted secret
cortex env set myapp SECRET_KEY "super-secret" --encrypt

# With validation
cortex env set myapp PORT 3000 --type port

# With description
cortex env set myapp LOG_LEVEL debug -d "Application logging level"
```

### Get a Variable

```bash
cortex env get <app> <KEY> [--decrypt]
```

**Options:**
- `--decrypt` - Decrypt and show encrypted values

**Examples:**

```bash
# Get a plain variable
cortex env get myapp DATABASE_URL
DATABASE_URL: postgres://localhost/db

# Get encrypted variable (shows [encrypted] by default)
cortex env get myapp API_KEY
API_KEY: [encrypted]

# Decrypt and show
cortex env get myapp API_KEY --decrypt
API_KEY: secret123
```

### List Variables

```bash
cortex env list <app> [--decrypt]
```

**Examples:**

```bash
cortex env list myapp
# Output:
# Environment: myapp
#   DATABASE_URL: postgres://localhost/db
#   API_KEY: [encrypted]
#   NODE_ENV: production
```

### Delete a Variable

```bash
cortex env delete <app> <KEY>
```

### Export Variables

Export environment variables in `.env` format:

```bash
cortex env export <app> [--include-encrypted] [--output FILE]
```

**Options:**
- `--include-encrypted` - Decrypt and include encrypted values
- `--output, -o` - Write to file instead of stdout

**Examples:**

```bash
# Export to stdout
cortex env export myapp

# Export to file
cortex env export myapp -o .env

# Include decrypted secrets (use with caution!)
cortex env export myapp --include-encrypted > .env
```

### Import Variables

Import from `.env` format:

```bash
cortex env import <app> [file] [--encrypt-keys KEYS]
```

**Options:**
- `--encrypt-keys` - Comma-separated list of keys to encrypt during import

**Examples:**

```bash
# Import from file
cortex env import myapp .env

# Import from stdin
cat .env | cortex env import myapp

# Import with selective encryption
cortex env import myapp .env --encrypt-keys "API_KEY,SECRET_KEY,DB_PASSWORD"
```

### Clear All Variables

```bash
cortex env clear <app> [--force]
```

**Options:**
- `--force, -f` - Skip confirmation prompt

### List Applications

```bash
cortex env apps
```

Shows all applications with stored environments.

### Load into Environment

Load variables into the current process's environment:

```bash
cortex env load <app>
```

This sets all variables in `os.environ`, decrypting encrypted values automatically.

## Templates

Templates provide pre-defined environment configurations for common frameworks.

### List Available Templates

```bash
cortex env template list
```

**Built-in Templates:**

| Template   | Description                        |
|------------|-----------------------------------|
| `nodejs`   | Standard Node.js application      |
| `python`   | Python application                |
| `django`   | Django web application            |
| `flask`    | Flask web application             |
| `docker`   | Docker containerized application  |
| `database` | Database connection               |
| `aws`      | AWS cloud services                |

### Show Template Details

```bash
cortex env template show <template>
```

**Example:**

```bash
cortex env template show django
# Output:
# Template: django
#   Django web application environment
#
# Variables:
#   * DJANGO_SETTINGS_MODULE (string)
#       Django settings module path
#   * SECRET_KEY (string)
#       Django secret key (should be encrypted)
#     DEBUG (boolean) = False
#       Django debug mode
#     ALLOWED_HOSTS (string) = localhost,127.0.0.1
#       Comma-separated allowed hosts
#     DATABASE_URL (url)
#       Database connection URL
#
# * = required
```

### Apply a Template

```bash
cortex env template apply <template> <app> [KEY=VALUE...] [--encrypt-keys KEYS]
```

**Examples:**

```bash
# Apply with defaults
cortex env template apply nodejs myapp

# Apply with custom values
cortex env template apply django myapp \
  DJANGO_SETTINGS_MODULE=myapp.settings \
  SECRET_KEY=my-secret-key \
  --encrypt-keys SECRET_KEY

# Override defaults
cortex env template apply nodejs myapp NODE_ENV=production PORT=8080
```

## Encryption

### How It Works

Cortex uses [Fernet symmetric encryption](https://cryptography.io/en/latest/fernet/) (AES-128-CBC with HMAC) from the `cryptography` library.

**Key Storage:**
- Encryption key is stored at `~/.cortex/.env_key`
- File permissions are set to `600` (owner read/write only)
- Key is automatically generated on first use

### Security Considerations

1. **Key Protection**: The encryption key must be protected. Anyone with access to `~/.cortex/.env_key` can decrypt all secrets.

2. **Backup**: If you lose the key file, encrypted values cannot be recovered. Consider backing up the key securely.

3. **Don't Commit**: Never commit `~/.cortex/` to version control.

4. **Export Caution**: Using `--include-encrypted` exposes secrets in plaintext.

### Rotating Keys

To rotate the encryption key:

```bash
# 1. Export all apps with decrypted values
for app in $(cortex env apps | grep -oP '^\s+\K\w+'); do
  cortex env export $app --include-encrypted > /tmp/${app}.env
done

# 2. Remove old key
rm ~/.cortex/.env_key

# 3. Re-import with new encryption
for app in $(cortex env apps | grep -oP '^\s+\K\w+'); do
  cortex env import $app /tmp/${app}.env --encrypt-keys "API_KEY,SECRET_KEY,PASSWORD"
done

# 4. Securely delete temp files
shred -u /tmp/*.env
```

## Validation

Variables can be validated against common types:

| Type      | Description                          | Example Values                    |
|-----------|--------------------------------------|-----------------------------------|
| `string`  | Any string (no validation)           | `hello`, `anything`               |
| `url`     | Valid URL with scheme                | `https://example.com`, `redis://localhost:6379` |
| `port`    | Port number (1-65535)                | `80`, `3000`, `8080`              |
| `boolean` | Boolean value                        | `true`, `false`, `1`, `0`, `yes`, `no` |
| `integer` | Integer number                       | `0`, `100`, `-5`                  |
| `path`    | File system path                     | `/usr/local/bin`, `./config`      |

**Example:**

```bash
# This succeeds
cortex env set myapp PORT 3000 --type port

# This fails with validation error
cortex env set myapp PORT 99999 --type port
Error: Invalid port number: 99999 (must be 1-65535)
```

## Integration with Services

### Loading at Service Start

Use `cortex env load` before starting your service:

```bash
# In your service startup script
cortex env load myapp && python app.py
```

### Python Integration

```python
from cortex.env_manager import get_env_manager

# Load environment for your app
env_mgr = get_env_manager()
env_mgr.load_to_environ("myapp")

# Now use os.environ normally
import os
database_url = os.environ.get("DATABASE_URL")
```

### Shell Script Integration

```bash
#!/bin/bash
# Load environment and run command
cortex env load myapp
exec "$@"
```

### Docker Integration

```dockerfile
# Install cortex in your image
RUN pip install cortex-linux

# Load env at runtime (requires mounted ~/.cortex)
ENTRYPOINT ["sh", "-c", "cortex env load myapp && exec \"$@\"", "--"]
CMD ["python", "app.py"]
```

## Best Practices

1. **Use Templates**: Start with a template and customize rather than creating from scratch.

2. **Encrypt Secrets**: Always use `--encrypt` for passwords, API keys, and sensitive data.

3. **Type Validation**: Use `--type` to catch configuration errors early.

4. **Document Variables**: Use `--description` to explain what each variable does.

5. **App Naming**: Use consistent, descriptive app names (e.g., `myapp-prod`, `myapp-dev`).

6. **Export Regularly**: Keep `.env` exports (without secrets) in version control as documentation.

7. **Audit Access**: Regularly review who has access to `~/.cortex/` on shared systems.

## Troubleshooting

### "cryptography package is required"

Install the cryptography library:

```bash
pip install cryptography
```

### "Variable not found"

Check that:
1. The app name is spelled correctly
2. The variable was set successfully
3. You're not confusing app names

```bash
# List all apps
cortex env apps

# List variables for specific app
cortex env list myapp
```

### "Invalid port/URL/boolean"

The value doesn't match the expected format. Check the validation rules above.

### "Decryption failed"

This usually means:
1. The encryption key (`~/.cortex/.env_key`) was changed or deleted
2. The encrypted value was corrupted
3. The value was encrypted with a different key

### Permission Denied

Check permissions on:
- `~/.cortex/` directory
- `~/.cortex/.env_key` file (should be 600)
- `~/.cortex/environments/` directory

```bash
chmod 700 ~/.cortex
chmod 600 ~/.cortex/.env_key
chmod 700 ~/.cortex/environments
```

## API Reference

For programmatic access, use the `EnvironmentManager` class:

```python
from cortex.env_manager import EnvironmentManager, get_env_manager

# Get default manager
env_mgr = get_env_manager()

# Or create custom instance
from cortex.env_manager import EnvironmentStorage, EncryptionManager
env_mgr = EnvironmentManager(
    storage=EnvironmentStorage(base_path="/custom/path"),
    encryption=EncryptionManager(key_path="/custom/key"),
)

# Set variables
env_mgr.set_variable("myapp", "KEY", "value", encrypt=True)

# Get variables
value = env_mgr.get_variable("myapp", "KEY", decrypt=True)

# List variables
for var in env_mgr.list_variables("myapp"):
    print(f"{var.key}: {var.value if not var.encrypted else '[encrypted]'}")

# Apply templates
result = env_mgr.apply_template("nodejs", "myapp", values={"PORT": "8080"})

# Export/Import
content = env_mgr.export_env("myapp", include_encrypted=True)
count, errors = env_mgr.import_env("myapp", content)

# Load to os.environ
env_mgr.load_to_environ("myapp")
```
