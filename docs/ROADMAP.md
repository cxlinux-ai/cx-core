# Cortex Linux - Improvement Roadmap

**Created:** November 2025
**Last Updated:** November 2025
**Status:** Active Development

---

## Priority Levels

| Level | Description | Timeline |
|-------|-------------|----------|
| 🔴 **Critical** | Security/breaking issues - fix immediately | 1-3 days |
| 🟠 **High** | Major improvements for quality and UX | 1-2 weeks |
| 🟡 **Medium** | Maintainability enhancements | 2-4 weeks |
| 🟢 **Low** | Nice-to-haves and polish | Ongoing |

---

## Phase 1: Critical Fixes (Days 1-3)

### 🔴 C-1: Fix Shell Injection Vulnerability
**File:** `cortex/coordinator.py`
**Lines:** 144-150
**Risk:** Commands from LLM can execute arbitrary shell code

**Before:**
```python
result = subprocess.run(
    step.command,
    shell=True,
    capture_output=True,
    text=True,
    timeout=self.timeout
)
```

**After:**
```python
import shlex

# Validate command first
validated_cmd = self._validate_and_sanitize(step.command)
result = subprocess.run(
    shlex.split(validated_cmd),
    shell=False,
    capture_output=True,
    text=True,
    timeout=self.timeout
)
```

**Effort:** 2-4 hours

---

### 🔴 C-2: Create Root requirements.txt
**Issue:** No root requirements file - installation fails

**Action:** Create `/requirements.txt`:
```
# Core dependencies
anthropic>=0.18.0
openai>=1.0.0

# Standard library extensions
typing-extensions>=4.0.0
```

**Effort:** 15 minutes

---

### 🔴 C-3: Fix CI/CD Pipeline
**File:** `.github/workflows/automation.yml`
**Issue:** Wrong directory name, silently passes failures

**Before:**
```yaml
if [ -d tests ]; then
  python -m pytest tests/ || echo "Tests not yet implemented"
```

**After:**
```yaml
- name: Install dependencies
  run: |
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    pip install pytest pytest-cov

- name: Run tests
  run: |
    python -m pytest test/ -v --cov=cortex --cov-report=xml

- name: Upload coverage
  uses: codecov/codecov-action@v3
```

**Effort:** 1-2 hours

---

## Phase 2: High Priority Improvements (Week 1-2)

### 🟠 H-1: Reorganize Directory Structure
**Current (Problematic):**
```
cortex/
├── cortex/          # Core module
├── LLM/             # Uppercase, separate
├── src/             # More modules here
├── test/            # Tests
├── *.py             # Root-level modules
└── *.sh             # Shell scripts
```

**Proposed:**
```
cortex/
├── cortex/
│   ├── __init__.py
│   ├── cli.py
│   ├── coordinator.py
│   ├── packages.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── interpreter.py
│   │   ├── router.py
│   │   └── providers/
│   ├── security/
│   │   ├── __init__.py
│   │   └── sandbox.py
│   ├── hardware/
│   │   ├── __init__.py
│   │   └── profiler.py
│   ├── history/
│   │   ├── __init__.py
│   │   └── tracker.py
│   └── utils/
│       ├── __init__.py
│       ├── logging.py
│       └── commands.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── docs/
├── scripts/
└── examples/
```

**Effort:** 4-8 hours

---

### 🟠 H-2: Add Comprehensive Installation Docs
**Create:** `docs/INSTALLATION.md`

**Content to include:**
- System requirements (Ubuntu 24.04+, Python 3.10+)
- Installing Firejail for sandbox support
- API key setup (OpenAI, Anthropic)
- Virtual environment setup
- First run verification
- Troubleshooting common issues

**Effort:** 2-3 hours

---

### 🟠 H-3: Extract Shared Command Utility
**Issue:** `_run_command()` duplicated in 4+ files

**Create:** `cortex/utils/commands.py`
```python
import subprocess
from typing import Tuple, List, Optional
from dataclasses import dataclass

@dataclass
class CommandResult:
    success: bool
    stdout: str
    stderr: str
    return_code: int

def run_command(
    cmd: List[str],
    timeout: int = 30,
    capture_output: bool = True
) -> CommandResult:
    """Execute a command safely with timeout."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            timeout=timeout
        )
        return CommandResult(
            success=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            return_code=result.returncode
        )
    except subprocess.TimeoutExpired:
        return CommandResult(False, "", "Command timed out", -1)
    except FileNotFoundError:
        return CommandResult(False, "", f"Command not found: {cmd[0]}", -1)
```

**Effort:** 2-3 hours

---

### 🟠 H-4: Add Dangerous Command Patterns
**File:** `src/sandbox_executor.py`
**Lines:** 114-125

**Add patterns:**
```python
DANGEROUS_PATTERNS = [
    # Existing patterns...
    r'rm\s+-rf\s+[/\*]',
    r'dd\s+if=',
    # NEW patterns to add:
    r'curl\s+.*\|\s*sh',
    r'wget\s+.*\|\s*sh',
    r'curl\s+.*\|\s*bash',
    r'wget\s+.*\|\s*bash',
    r'\beval\s+',
    r'python\s+-c\s+["\'].*exec',
    r'base64\s+-d\s+.*\|',
    r'>\s*/etc/',
    r'chmod\s+777',
    r'chmod\s+\+s',
]
```

**Effort:** 1 hour

---

### 🟠 H-5: Implement API Retry Logic
**File:** `LLM/interpreter.py`

**Add retry decorator:**
```python
import time
from functools import wraps

def retry_with_backoff(max_retries=3, base_delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (RuntimeError, ConnectionError) as e:
                    if attempt == max_retries - 1:
                        raise
                    delay = base_delay * (2 ** attempt)
                    time.sleep(delay)
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

**Effort:** 1-2 hours

---

### 🟠 H-6: Standardize Python Version
**Files to update:**
- `setup.py`: Change to `python_requires=">=3.10"`
- `README.md`: Update to "Python 3.10+"
- `.github/workflows/automation.yml`: Test on 3.10, 3.11, 3.12

**Effort:** 30 minutes

---

### 🟠 H-7: Add Security Scanning to CI
**File:** `.github/workflows/automation.yml`

**Add jobs:**
```yaml
security:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v3
    - name: Run Bandit
      run: |
        pip install bandit
        bandit -r cortex/ -ll

    - name: Check dependencies
      run: |
        pip install safety
        safety check -r requirements.txt
```

**Effort:** 1 hour

---

### 🟠 H-8: Add Input Validation
**All user-facing functions need validation**

**Example for `cli.py`:**
```python
import re

def validate_software_name(name: str) -> str:
    """Validate and sanitize software name input."""
    if not name or not name.strip():
        raise ValueError("Software name cannot be empty")

    # Remove potentially dangerous characters
    sanitized = re.sub(r'[;&|`$]', '', name)

    # Limit length
    if len(sanitized) > 200:
        raise ValueError("Software name too long")

    return sanitized.strip()
```

**Effort:** 2-3 hours

---

## Phase 3: Medium Priority (Weeks 2-4)

### 🟡 M-1: Implement Dependency Injection
**Pattern to follow:**

```python
# Before (hard coupling)
class CortexCLI:
    def install(self, software):
        interpreter = CommandInterpreter(api_key=self._get_api_key())

# After (dependency injection)
class CortexCLI:
    def __init__(self, interpreter: Optional[CommandInterpreter] = None):
        self._interpreter = interpreter

    def install(self, software):
        interpreter = self._interpreter or CommandInterpreter(...)
```

**Effort:** 4-6 hours

---

### 🟡 M-2: Centralize Logging Configuration
**Create:** `cortex/utils/logging.py`

```python
import logging
import sys
from pathlib import Path

def setup_logging(
    level: int = logging.INFO,
    log_file: Optional[Path] = None
) -> logging.Logger:
    """Configure logging for the entire application."""
    logger = logging.getLogger('cortex')
    logger.setLevel(level)

    # Console handler
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter(
        '%(levelname)s: %(message)s'
    ))
    logger.addHandler(console)

    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(file_handler)

    return logger
```

**Effort:** 2-3 hours

---

### 🟡 M-3: Add Test Coverage Targets
**Update CI to enforce coverage:**

```yaml
- name: Check coverage
  run: |
    coverage=$(python -m pytest --cov=cortex --cov-fail-under=70)
```

**Target milestones:**
- Week 2: 60% coverage
- Week 4: 70% coverage
- Week 8: 80% coverage

**Effort:** Ongoing

---

### 🟡 M-4: Add Integration Tests
**Create:** `tests/integration/test_install_flow.py`

```python
import pytest
from unittest.mock import Mock, patch

class TestInstallationFlow:
    """End-to-end installation flow tests."""

    @pytest.fixture
    def mock_api(self):
        with patch('cortex.llm.interpreter.OpenAI') as mock:
            yield mock

    def test_full_install_dry_run(self, mock_api):
        """Test complete installation flow in dry-run mode."""
        # Setup
        mock_api.return_value.chat.completions.create.return_value = ...

        # Execute
        result = cli.install("docker", dry_run=True)

        # Verify
        assert result == 0
```

**Effort:** 4-6 hours

---

### 🟡 M-5: Implement Response Caching
**Create:** `cortex/utils/cache.py`

```python
from functools import lru_cache
from typing import Optional
import hashlib

class LLMCache:
    """Simple cache for LLM responses."""

    def __init__(self, max_size: int = 100):
        self._cache = {}
        self._max_size = max_size

    def get(self, prompt: str) -> Optional[str]:
        key = hashlib.sha256(prompt.encode()).hexdigest()
        return self._cache.get(key)

    def set(self, prompt: str, response: str) -> None:
        if len(self._cache) >= self._max_size:
            # Remove oldest entry
            self._cache.pop(next(iter(self._cache)))
        key = hashlib.sha256(prompt.encode()).hexdigest()
        self._cache[key] = response
```

**Effort:** 2-3 hours

---

### 🟡 M-6: Add Type Hints Throughout
**Files needing type hints:**
- `cortex/cli.py` - return types
- `context_memory.py` - all methods
- `logging_system.py` - all methods

**Run mypy:**
```bash
mypy cortex/ --ignore-missing-imports
```

**Effort:** 3-4 hours

---

### 🟡 M-7: Remove Duplicate Files
**Delete:**
- `deploy_jesse_system (1).sh`
- `README_DEPENDENCIES (1).md`

**Effort:** 5 minutes

---

### 🟡 M-8: Use XDG Base Directory Standard
**Current:** `/var/lib/cortex/history.db`
**Should be:** `~/.local/share/cortex/history.db`

```python
from pathlib import Path
import os

def get_data_dir() -> Path:
    """Get XDG-compliant data directory."""
    xdg_data = os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')
    data_dir = Path(xdg_data) / 'cortex'
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
```

**Effort:** 1 hour

---

## Phase 4: Low Priority (Ongoing)

### 🟢 L-1: Add Architecture Diagrams
Create Mermaid diagrams in `docs/ARCHITECTURE.md`

### 🟢 L-2: Add Async Support
Convert I/O operations to async for better performance

### 🟢 L-3: Plugin Architecture
Allow custom LLM providers and package managers

### 🟢 L-4: Add Telemetry (Opt-in)
Anonymous usage statistics for improvement

### 🟢 L-5: Interactive Mode
REPL-style interface for multi-step operations

### 🟢 L-6: Shell Completion
Add bash/zsh completions for CLI

### 🟢 L-7: Man Pages
Generate man pages from docstrings

### 🟢 L-8: Docker Development Environment
Dockerfile for consistent development

---

## Implementation Timeline

```
Week 1:
├── Day 1-2: C-1 (Shell injection fix)
├── Day 2: C-2 (requirements.txt)
├── Day 3: C-3 (CI/CD fix)
└── Day 3-5: H-1 (Directory structure)

Week 2:
├── H-2 (Installation docs)
├── H-3 (Command utility)
├── H-4 (Dangerous patterns)
└── H-5 (Retry logic)

Week 3:
├── H-6, H-7, H-8 (Standards & validation)
├── M-1 (Dependency injection)
└── M-2 (Logging)

Week 4:
├── M-3, M-4 (Tests)
├── M-5 (Caching)
└── M-6 (Type hints)

Ongoing:
└── Low priority items as time permits
```

---

## Success Metrics

| Metric | Current | Target | Timeline |
|--------|---------|--------|----------|
| Test Coverage | ~45% | 80% | 4 weeks |
| Security Issues | 3 critical | 0 critical | 1 week |
| Documentation | Incomplete | Complete | 2 weeks |
| CI Pass Rate | Unknown | >95% | 1 week |
| Type Coverage | ~30% | 80% | 4 weeks |

---

## Resources Needed

- **Development:** 1-2 developers, 40-80 hours total
- **Review:** Security audit recommended after Phase 2
- **Testing:** Manual testing on Ubuntu 24.04

---

*This roadmap is a living document. Update as progress is made.*
