# Security Policy

## Supported Versions

CX Terminal is currently in active development. Security updates are provided for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it responsibly.

### How to Report

**DO NOT** open a public GitHub issue for security vulnerabilities.

Instead, please email: **security@cxlinux.ai**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### What to Expect

| Timeline | Action |
|----------|--------|
| 24 hours | Acknowledgment of your report |
| 72 hours | Initial assessment and severity rating |
| 7 days   | Status update on fix progress |
| 30 days  | Target resolution for critical issues |
| 90 days  | Target resolution for non-critical issues |

### Severity Ratings

| Severity | Description | Response Time |
|----------|-------------|---------------|
| **Critical** | Remote code execution, privilege escalation, data breach | 24-48 hours |
| **High** | Authentication bypass, significant data exposure | 7 days |
| **Medium** | Limited data exposure, denial of service | 30 days |
| **Low** | Minor issues, hardening improvements | 90 days |

### Scope

Security concerns for CX Terminal include:

- **AI Command Execution** — Sandboxing and validation of AI-generated commands
- **IPC Security** — Unix socket communication with cx-daemon
- **Credential Handling** — API keys, SSH keys, secrets in terminal sessions
- **Local Data** — SQLite history database, ML models, configuration files
- **Network Security** — LLM API communications, update mechanisms

### Out of Scope

- Vulnerabilities in upstream WezTerm (report to [WezTerm](https://github.com/wez/wezterm))
- Social engineering attacks
- Physical access attacks
- Denial of service via resource exhaustion

### Recognition

We gratefully acknowledge security researchers who report vulnerabilities responsibly. With your permission, we will:

- Credit you in the security advisory
- Add you to our Security Hall of Fame
- Provide bounty consideration for critical findings (post-funding)

### Safe Harbor

We support responsible disclosure. We will not pursue legal action against researchers who:

- Act in good faith
- Avoid privacy violations, data destruction, and service disruption
- Report vulnerabilities promptly
- Allow reasonable time for remediation before disclosure

## Security Best Practices

When using CX Terminal:

1. **Review AI commands** — Always use dry-run mode for destructive operations
2. **Protect API keys** — Use environment variables, not hardcoded values
3. **Update regularly** — Security patches are released as needed
4. **Audit logs** — Review `~/.cx/history.db` periodically
5. **Network isolation** — Use firewall rules for cx-daemon if exposed

---

**Contact:** security@cxlinux.ai  
**PGP Key:** [Coming soon]  
**Last Updated:** January 2026
EOF
