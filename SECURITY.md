# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.x.x   | :white_check_mark: |

## Reporting a Vulnerability

**DO NOT** open a public GitHub issue for security vulnerabilities.

Instead, email: **security@cortexlinux.com**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact

### Response Timeline

| Timeline | Action |
|----------|--------|
| 24 hours | Initial acknowledgment |
| 72 hours | Severity assessment |
| 7 days | Status update |
| 30 days | Target patch release |

### Scope

**In scope:**
- Cortex CLI - Command injection, privilege escalation
- API Key handling - Exposure, insecure storage
- Sandbox escapes - Firejail bypass
- Dependency vulnerabilities - Critical CVEs

**Out of scope:**
- Third-party dependencies (report to maintainers)
- Social engineering attacks
- Denial of service (unless trivially exploitable)

### Safe Harbor

Security research conducted in good faith is authorized. We will not pursue legal action against researchers who:
- Avoid privacy violations
- Don't destroy data
- Report findings promptly

## Security Best Practices
```bash
# Store API key securely
read -s ANTHROPIC_API_KEY && export ANTHROPIC_API_KEY

# Always preview before executing
cortex install <package> --dry-run
```

## Contact

security@cortexlinux.com
