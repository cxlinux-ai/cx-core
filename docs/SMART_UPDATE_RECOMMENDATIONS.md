# Smart Update Recommendations

## Overview

Cortex's Smart Update Recommender is an AI-powered system that analyzes your installed packages, checks for available updates, and provides intelligent recommendations on **when** and **what** to update.

## Features

- **Scan for Available Updates**: Automatically detects packages with pending updates
- **Risk Assessment**: Evaluates each update's potential impact on your system
- **Timing Recommendations**: Suggests optimal update windows based on risk level
- **Related Updates Grouping**: Groups updates for related packages (e.g., all PostgreSQL components)
- **Breaking Change Prediction**: Identifies potential breaking changes from major version updates
- **LLM Integration**: Uses AI to provide additional context and analysis

## Usage

### Basic Command

```bash
cortex update recommend
```

### Example Output

```text
📊 Update Analysis

🔒 Security Updates (Apply ASAP):
   - openssl 1.1.1t → 1.1.1u (CVE-2024-1234)

✅ Safe to Update Now (Low Risk):
   - nginx 1.24.0 → 1.25.0 (minor, security fix)
   - curl 8.4.0 → 8.5.0 (patch, bug fixes)

📅 Recommended for Maintenance Window:
   - python3 3.11.4 → 3.11.6 (minor)
   - nodejs 18.18.0 → 20.10.0 (major version)

⏸️ Hold for Now:
   - postgresql 14.10 → 15.5 (major version, database migration required)
   - docker 24.0 → 25.0 (major, wait for stability reports)

📦 Related Update Groups:
   - postgresql: postgresql, postgresql-client, postgresql-contrib
   - docker: docker.io, containerd

🤖 AI Analysis:
   Most updates are safe to apply. However, the PostgreSQL update requires
   a major version migration. Consider backing up your databases before
   proceeding. The Docker update should be deferred until version 25.0.1
   addresses reported container networking issues.
```

### Command Options

| Option | Description |
|--------|-------------|
| `--no-llm` | Disable LLM-powered analysis (faster, works offline) |
| `--json` | Output recommendations in JSON format for scripting |

### JSON Output Example

```bash
cortex update recommend --json
```

```json
{
  "timestamp": "2024-01-15T10:30:00",
  "total_updates": 8,
  "overall_risk": "medium",
  "security_updates": [
    {
      "package": "openssl",
      "current": "1.1.1t",
      "new": "1.1.1u",
      "risk": "low",
      "type": "patch"
    }
  ],
  "immediate_updates": [...],
  "scheduled_updates": [...],
  "deferred_updates": [
    {
      "package": "postgresql",
      "current": "14.10",
      "new": "15.5",
      "risk": "high",
      "type": "major",
      "breaking_changes": [
        "Major version change (14 → 15)",
        "Database - may require dump/restore"
      ]
    }
  ],
  "groups": {
    "postgresql": ["postgresql", "postgresql-client", "postgresql-contrib"]
  },
  "llm_analysis": "..."
}
```

## Update Categories

### 🔒 Security Updates
Priority: **Critical** - Apply as soon as possible

These updates address known security vulnerabilities. They are typically:
- Patched for specific CVEs
- Low risk to system stability
- Essential for system security

**Recommended Action**: Apply immediately, ideally within 24-48 hours.

### ✅ Safe to Update Now (Immediate)
Priority: **Low Risk** - Safe for immediate installation

Updates in this category:
- Are patch or minor version updates
- Have no known breaking changes
- Don't affect critical system components

**Recommended Action**: Apply at your convenience.

### 📅 Recommended for Maintenance Window (Scheduled)
Priority: **Medium Risk** - Plan for scheduled maintenance

These updates:
- May require service restarts
- Could have minor compatibility changes
- Include new features that may affect workflows

**Recommended Action**: Apply during planned maintenance windows, preferably off-peak hours.

### ⏸️ Hold for Now (Deferred)
Priority: **High Risk** - Exercise caution

Updates flagged for deferral:
- Are major version upgrades
- May include breaking changes
- Affect critical infrastructure (databases, kernel, etc.)
- Are pre-release or recently released versions

**Recommended Action**: Wait for stability reports, plan migration carefully, and test in staging environment first.

## Risk Assessment Criteria

The risk level is determined by multiple factors:

| Factor | Impact on Risk |
|--------|---------------|
| **Version Change Type** | |
| - Patch (X.Y.Z → X.Y.Z+1) | Low (+5) |
| - Minor (X.Y → X.Y+1) | Low-Medium (+15) |
| - Major (X → X+1) | High (+40) |
| **Package Importance** | |
| - Kernel (linux-image) | High (+30) |
| - Core libraries (glibc, libc6) | High (+30) |
| - System services (systemd) | High (+30) |
| - Databases (postgresql, mysql) | High (+30) |
| **Version Stability** | |
| - Pre-release (alpha, beta, rc) | High (+25) |
| **Changelog Analysis** | |
| - Mentions "breaking change" | Medium (+15) |
| - Mentions "deprecated" | Medium (+15) |
| - Mentions "migration required" | Medium (+15) |

### Risk Score Thresholds

- **Low**: Score < 15
- **Medium**: Score 15-34
- **High**: Score ≥ 35

## Package Grouping

Related packages are automatically grouped to help you update them together:

| Group | Packages |
|-------|----------|
| `python` | python3, python3-pip, python3-dev |
| `docker` | docker.io, docker-ce, containerd |
| `postgresql` | postgresql, postgresql-client, postgresql-contrib |
| `mysql` | mysql-server, mysql-client, mariadb-server |
| `nginx` | nginx, nginx-common, nginx-core |
| `nodejs` | nodejs, npm, node-gyp |
| `kernel` | linux-image, linux-headers, linux-modules |
| `ssl` | openssl, libssl-dev, ca-certificates |

## Update Strategies

### Strategy 1: Rolling Updates (Recommended for Most Users)

1. **Daily**: Apply security updates
2. **Weekly**: Apply low-risk immediate updates
3. **Monthly**: Apply scheduled updates during maintenance window
4. **Quarterly**: Evaluate and plan deferred updates

### Strategy 2: Stability-First (Production Servers)

1. Test all updates in staging environment first
2. Apply security updates within 48 hours
3. Batch other updates monthly
4. Defer major version updates until stability is confirmed

### Strategy 3: Always Current (Development Machines)

1. Apply immediate and scheduled updates weekly
2. Consider early adoption of deferred updates for testing
3. Keep multiple system snapshots for quick rollback

## Best Practices

### Before Updating

1. **Back up critical data**: Especially before database or kernel updates
2. **Check changelogs**: Review breaking changes for deferred updates
3. **Test in staging**: Major updates should be tested first
4. **Plan rollback**: Know how to revert if issues arise

### After Updating

1. **Verify services**: Check that critical services are running
2. **Monitor logs**: Watch for errors in system and application logs
3. **Test functionality**: Validate key workflows still work
4. **Document changes**: Keep record of what was updated and when

### For Major Version Updates

1. **Read migration guides**: Official documentation often provides migration steps
2. **Check compatibility**: Ensure dependent applications support the new version
3. **Schedule downtime**: Major updates may require service interruption
4. **Have a rollback plan**: Snapshot VMs or have package backups ready

## Integration with Other Tools

### Cron-based Automation

```bash
# Check for updates daily and log results
0 8 * * * /usr/local/bin/cortex update recommend --no-llm --json >> /var/log/cortex-updates.json
```

### CI/CD Pipelines

```yaml
# GitHub Actions example
- name: Check for system updates
  run: |
    cortex update recommend --json > updates.json
    if jq -e '.security_updates | length > 0' updates.json; then
      echo "::warning::Security updates available"
    fi
```

## Troubleshooting

### "No updates available"
- Run `sudo apt update` or equivalent to refresh package cache
- Check network connectivity to package repositories

### LLM analysis not working
- Use `--no-llm` flag for offline operation
- Check API key configuration with `cortex config show`

### Slow analysis
- Large number of updates may take time
- Use `--no-llm` for faster results without AI analysis

## See Also

- `cortex update check` - Check for Cortex self-updates
- `cortex update install` - Install Cortex updates
- `cortex install` - Install system packages with AI assistance
