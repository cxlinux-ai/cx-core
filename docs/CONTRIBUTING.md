# Contributing to Cortex Linux

Thank you for your interest in contributing to Cortex Linux! This document provides guidelines and instructions for contributing.

## Code of Conduct

Please be respectful, professional, and inclusive in all interactions. We aim to create a welcoming environment for all contributors.

## Getting Started

### Prerequisites

- Debian 12+ or Ubuntu 24.04+ build host
- Root/sudo access for live-build
- ~10GB free disk space
- Internet connection (for package downloads)
- Git for version control

### Setting Up Development Environment

1. **Clone the repository**:
   ```bash
   git clone https://github.com/cortexlinux/cortex-distro.git
   cd cortex-distro
   ```

2. **Install build dependencies**:
   ```bash
   make deps
   # Or manually:
   sudo apt-get install live-build debootstrap squashfs-tools xorriso \
       isolinux syslinux-efi grub-pc-bin grub-efi-amd64-bin \
       mtools dosfstools dpkg-dev devscripts debhelper fakeroot gnupg
   ```

3. **Build a test ISO**:
   ```bash
   make iso
   ```

## Development Workflow

### 1. Fork and Branch

1. Fork the repository on GitHub
2. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

### 2. Make Changes

- Make your changes
- Follow coding style (see below)
- Test your changes
- Update documentation as needed

### 3. Test Changes

Run tests before submitting:
```bash
make test
```

Test specific components:
```bash
# Test packages
./tests/verify-packages.sh

# Test preseed
./tests/verify-preseed.sh

# Test ISO (if built)
./tests/verify-iso.sh output/cortex-linux-*.iso
```

### 4. Commit Changes

Write clear, descriptive commit messages:
```bash
git commit -m "Add feature: brief description

More detailed explanation of what was changed and why."
```

### 5. Submit Pull Request

1. Push to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

2. Create a Pull Request on GitHub
3. Fill out the PR template
4. Wait for review

## Coding Style

### Bash Scripts

- Use `#!/bin/bash` shebang
- Use `set -e` for error handling
- Use `set -u` for undefined variable detection (where appropriate)
- Quote all variables: `"$variable"`
- Use meaningful variable names
- Add comments for complex logic
- Follow existing script structure

Example:
```bash
#!/bin/bash
# Script description
# Copyright 2025 AI Venture Holdings LLC
# SPDX-License-Identifier: Apache-2.0

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Function with description
do_something() {
    local arg="$1"
    echo "Processing: $arg"
}
```

### Debian Packages

- Follow Debian packaging guidelines
- Use `debian/rules` for build logic
- Provide proper `debian/control` metadata
- Include changelog entries
- Test packages with lintian

### Documentation

- Use Markdown for documentation
- Follow existing documentation style
- Include code examples
- Keep documentation up to date

## Areas for Contribution

### High Priority

1. **Branding Assets**
   - Plymouth boot splash theme
   - Desktop wallpapers
   - Logo files (SVG, PNG)
   - Icon sets

2. **Testing**
   - Expand test coverage
   - Add integration tests
   - Improve verification scripts

3. **Documentation**
   - User guides
   - Developer documentation
   - API documentation
   - Tutorials

4. **Onboarding**
   - Improve first-boot experience
   - Add welcome screens
   - Enhance user feedback

### General Contributions

- Bug fixes
- Feature additions
- Performance improvements
- Security enhancements
- Code cleanup and refactoring
- Documentation improvements

## Testing Guidelines

### Package Tests

- Verify package structure
- Check dependencies
- Test installation/removal
- Validate configuration files

### Preseed Tests

- Validate preseed syntax
- Test automated installation
- Verify configuration options
- Check security settings

### ISO Tests

- Verify ISO integrity
- Test bootability (UEFI/BIOS)
- Check file structure
- Validate checksums

## Submission Guidelines

### Pull Request Checklist

- [ ] Code follows style guidelines
- [ ] Tests pass locally
- [ ] Documentation updated
- [ ] Commit messages are clear
- [ ] Changes are tested
- [ ] No breaking changes (or documented)

### Pull Request Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Refactoring
- [ ] Other (describe)

## Testing
How was this tested?

## Checklist
- [ ] Code follows style guidelines
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No breaking changes
```

## Review Process

1. **Initial Review**: Maintainers review PR
2. **Feedback**: Address review comments
3. **Testing**: Changes tested by maintainers
4. **Approval**: PR approved and merged

## Building and Releasing

### Build Process

1. Build packages: `make package`
2. Build ISO: `make iso`
3. Generate SBOM: `make sbom`
4. Run tests: `make test`

### Release Process

(Handled by maintainers)

1. Update version numbers
2. Generate changelog
3. Build release artifacts
4. Sign artifacts
5. Publish release
6. Announce release

## Getting Help

- **Documentation**: https://cortexlinux.com/docs
- **GitHub Issues**: https://github.com/cortexlinux/cortex-distro/issues
- **Discord**: https://discord.gg/cortexlinux
- **Email**: team@cortexlinux.com

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 license, the same as Cortex Linux.

---

Thank you for contributing to Cortex Linux! 🚀
