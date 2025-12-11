# Installation Verification System

Validates that software installations completed successfully.

## Features

- ✅ Command execution verification
- ✅ File/binary existence checks
- ✅ Service status validation
- ✅ Version matching
- ✅ Supports 10+ common packages out-of-the-box
- ✅ Custom test definitions
- ✅ JSON export for automation
- ✅ Detailed error reporting

## Usage

### Basic Verification

```bash
# Verify single package
python3 installation_verifier.py nginx

# Verify multiple packages
python3 installation_verifier.py nginx postgresql redis-server
```

### With Options

```bash
# Detailed output
python3 installation_verifier.py docker --detailed

# Export results
python3 installation_verifier.py mysql-server --export results.json

# Check specific version
python3 installation_verifier.py nodejs --version 18.0.0
```

### Programmatic Usage

```python
from installation_verifier import InstallationVerifier, VerificationStatus

verifier = InstallationVerifier()

# Verify package
result = verifier.verify_package('nginx')

if result.status == VerificationStatus.SUCCESS:
    print(f"✅ {result.overall_message}")
else:
    print(f"❌ Verification failed")
    for test in result.tests:
        if not test.passed:
            print(f"  - {test.name}: {test.error_message}")

# Custom tests
custom_tests = [
    {'type': 'command', 'command': 'myapp --version'},
    {'type': 'file', 'path': '/etc/myapp/config.yml'},
    {'type': 'service', 'name': 'myapp'}
]

result = verifier.verify_package(
    'myapp',
    custom_tests=custom_tests
)
```

## Supported Packages

Out-of-the-box support for:
- nginx
- apache2
- postgresql
- mysql-server
- docker
- python3
- nodejs
- redis-server
- git
- curl

## Testing

```bash
python3 test_installation_verifier.py
```

## Integration with Cortex

```python
# After installation
from installation_verifier import InstallationVerifier, VerificationStatus

verifier = InstallationVerifier()
result = verifier.verify_package(installed_package)

if result.status != VerificationStatus.SUCCESS:
    # Trigger auto-fix or notify user
    handle_installation_failure(result)
```

## Exit Codes

- `0`: All verifications passed
- `1`: One or more verifications failed

## Example Output

```
🔍 Verifying 3 package(s)...

  Checking nginx...
  ✅ nginx installed and verified successfully

  Checking postgresql...
  ✅ postgresql installed and verified successfully

  Checking docker...
  ✅ docker installed and verified successfully

============================================================
VERIFICATION SUMMARY
============================================================
Total packages: 3
✅ Success: 3
❌ Failed: 0
⚠️ Partial: 0
❓ Unknown: 0
```

## Architecture

### VerificationTest
Individual test with pass/fail status:
- Command execution
- File existence
- Service status
- Version matching

### VerificationResult
Complete verification with multiple tests:
- Overall status (SUCCESS/FAILED/PARTIAL/UNKNOWN)
- Detailed test results
- Timestamp
- Error messages

### InstallationVerifier
Main class that orchestrates verification:
- Runs multiple test types
- Generates recommendations
- Exports to JSON
- CLI interface

## Contributing

To add support for a new package, update the `VERIFICATION_PATTERNS` dictionary in `installation_verifier.py`:

```python
VERIFICATION_PATTERNS = {
    'your-package': {
        'command': 'your-package --version',
        'file': '/usr/bin/your-package',
        'service': 'your-package',
        'version_regex': r'version (\d+\.\d+\.\d+)'
    }
}
```

## License

MIT License - Part of Cortex Linux
