# Security Policy

## Supported Versions

Use this section to tell people about which versions of your project are
currently being supported with security updates.

| Version | Supported          # Security Policy

## Supported Versions

CX Linux is currently in active development. Security updates are provided for the following versions:

| Version | Supported          | Notes |
| ------- | ------------------ | ----- |
| 0.9.x   | :white_check_mark: | Current stable release |
| 0.8.x   | :white_check_mark: | Security patches only |
| < 0.8   | :x:                | End of life |

## Security Model

CX Linux implements defense-in-depth security:

| Layer | Protection |
|-------|------------|
| **Sandboxing** | All AI-generated commands run in Firejail isolation |
| **Dry-run default** | Destructive operations require explicit confirmation |
| **Privilege separation** | Daemon runs unprivileged; PolicyKit for sudo |
| **Input sanitization** | Command injection prevention on all user input |
| **Audit logging** | All operations logged with timestamps |

## Reporting a Vulnerability

**Do NOT open a public GitHub issue for security vulnerabilities.**

### How to Report

Email: **security@cortexlinux.com**

Include:
- Description of the vulnerability
- Steps to reproduce
- Affected version(s)
- Potential impact assessment
- Any suggested fixes (optional)

### What to Expect

| Timeframe | Action |
|-----------|--------|
| **24 hours** | Acknowledgment of report received |
| **72 hours** | Initial assessment and severity classification |
| **7 days** | Status update with remediation plan |
| **30 days** | Target resolution for critical/high severity |
| **90 days** | Target resolution for medium/low severity |

### Severity Classification

| Severity | Description | Response Time |
|----------|-------------|---------------|
| **Critical** | Remote code execution, privilege escalation | 24-48 hours |
| **High** | Command injection, sandbox escape | 7 days |
| **Medium** | Information disclosure, DoS | 30 days |
| **Low** | Minor issues, hardening improvements | 90 days |

### Recognition

We maintain a security acknowledgments page for responsible disclosures. Reporters may opt for:
- Public credit with name/handle
- Anonymous acknowledgment
- No public mention

### Bug Bounty

We do not currently operate a paid bug bounty program. This may change post-funding.

## Security Best Practices for Users

1. **Keep CX Linux updated** — Run `cx update` regularly
2. **Review dry-run output** — Always verify before confirming destructive operations
3. **Use minimal privileges** — Don't run CX daemon as root
4. **Protect API keys** — Store Claude API key in environment variables, not config files
5. **Monitor audit logs** — Review `~/.cx/logs/audit.log` periodically

## Vulnerability Disclosure Policy

We follow coordinated disclosure:

- Reporters give us reasonable time to fix before public disclosure
- We credit reporters in release notes (unless anonymity requested)
- We do not pursue legal action against good-faith security researchers

## Contact

| Channel | Use For |
|---------|---------|
| security@cortexlinux.com | Vulnerability reports |
| https://github.com/cxlinux-ai/cx/issues | Non-security bugs |
| https://discord.gg/uCqHvxjU83 | General support |

---

**Last Updated:** January 2026  
**Policy Version:** 1.0
| ------- | ------------------ |
| 5.1.x   | :white_check_mark: |
| 5.0.x   | :x:                |
| 4.0.x   | :white_check_mark: |
| < 4.0   | :x:                |

## Reporting a Vulnerability

Use this section to tell people how to report a vulnerability.

Tell them where to go, how often they can expect to get an update on a
reported vulnerability, what to expect if the vulnerability is accepted or
declined, etc.
