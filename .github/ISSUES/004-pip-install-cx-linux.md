# Issue: Create `pip install cx-linux` Package

**Priority:** High
**Labels:** packaging, distribution
**Milestone:** v0.2.0 Identity Reset

## Summary

Publish the CX CLI to PyPI as `cx-linux` for easy installation via pip.

## Rationale

- Lowest friction installation method
- Works on any system with Python
- Standard distribution channel developers trust
- Enables viral growth: "just `pip install cx-linux`"

## Package Details

**Name:** `cx-linux`
**Command:** `cx`
**Python:** 3.10+

## Installation Experience

```bash
# Install
pip install cx-linux

# Verify
cx --version
CX Linux v0.2.0 - AI Agents for Linux Administration

# First use
cx ask "How do I check disk space?"
```

## Changes Required

### 1. pyproject.toml / setup.py
```toml
[project]
name = "cx-linux"
version = "0.2.0"
description = "AI Agents for Linux Administration"
authors = [{name = "CX Linux", email = "support@cxlinux.com"}]
license = {text = "BSL-1.1"}
readme = "README.md"
requires-python = ">=3.10"
keywords = ["linux", "ai", "agents", "administration", "cli"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Intended Audience :: System Administrators",
    "License :: Other/Proprietary License",
    "Operating System :: POSIX :: Linux",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: System :: Systems Administration",
]

[project.scripts]
cx = "cx.main:main"
```

### 2. Directory Structure
```
cx-linux/
├── cx/
│   ├── __init__.py
│   ├── main.py
│   ├── ask.py
│   ├── agents/
│   └── ...
├── pyproject.toml
├── README.md
└── LICENSE
```

### 3. CI/CD
- [ ] GitHub Action to publish to PyPI on release
- [ ] Test installation in clean environments
- [ ] Version bump automation

## Acceptance Criteria

- [ ] `pip install cx-linux` works on Linux/macOS
- [ ] `cx` command available after install
- [ ] Dependencies correctly specified
- [ ] README renders correctly on PyPI
- [ ] License clearly stated
