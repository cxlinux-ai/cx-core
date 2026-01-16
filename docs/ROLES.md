# System Role Management

Manage system personalities and receive tailored package recommendations based on your workstation's specific purpose, powered by autonomous AI context sensing.

## Overview

Cortex utilizes an AI-first approach to understand the technical context of your Linux environment. Instead of relying on static rules or hardcoded mappings, Cortex acts as a sensing layer—identifying existing software signals, hardware capabilities, and operational history—to provide an LLM with a factual ground truth for inferring the most appropriate system role.

The `cortex role` command group handles the factual gathering of system context, secure redaction of sensitive data, and thread-safe persistence of AI-driven classifications.

## Usage

### Basic Commands

```bash
# Auto-detect your system role using AI analysis of local context and history
cortex role detect

# Manually set your system role to receive specific AI recommendations
cortex role set ml-workstation

# View help for the role command group
cortex role --help
```

## Features

### 1. Architectural Context Sensing

Cortex scans your system `PATH` for signature binaries (such as `docker`, `kubectl`, or `terraform`) and performs deep hardware detection for NVIDIA (CUDA), AMD (ROCm), and Intel GPU architectures to ensure recommendations are optimized for your specific silicon.

### 2. Operational History Learning

By analyzing recent command patterns and deployment history, Cortex allows the AI Architect to "learn" from your unique workflow. It identifies repetitive technical behaviors to recommend specific packages that improve productivity.

### 3. PII Redaction & Privacy

Security is a core component of the sensing layer. Before operational history is sent for AI inference, all data is passed through a hardened PII Redaction Layer. Advanced Regex patterns sanitize shell history to ensure API keys, tokens, environment exports, and secrets are never transmitted.

### 4. High Reliability & Coverage

The role management system is backed by a robust test suite ensuring thread-safety and accurate fact gathering.

* Test Coverage: 91.11%
* Persistence: Thread-safe `fcntl` locking for environment consistency.

## Examples

### AI Detection Audit

```bash
$ cortex role detect

🧠 AI is sensing system context and activity patterns...

Detected roles:
  1. DevOps Engineer
  2. Data Scientist
  3. System Architect

💡 To install any recommended packages, simply run:
    cortex install <package_name>
```

### Manually Transitioning Personas

```bash
$ cortex role set data-analysis

✓ Role set to: data-analysis

🔍 Fetching tailored AI recommendations for data-analysis...

💡 Recommended packages for data-analysis:
  - pandas
  - numpy
  - matplotlib
  - scikit-learn

💡 Ready to upgrade? Install any of these using:
    cortex install <package_name>
```

## Technical Implementation

### Visible Cache Busting

To ensure recommendations are always fresh and reflect the current system state, Cortex implements a high-precision cache-busting mechanism. Every AI query includes a unique `req_id` generated from microsecond timestamps and UUID fragments, forcing the LLM to perform unique inference for every request.

### Thread-Safe Persistence

Cortex utilizes `fcntl` for advisory record locking and an atomic swap pattern to ensure your active role state remains consistent across multiple concurrent CLI sessions without risk of file corruption.

```python
# Atomic write pattern with module-consistent type hinting
from typing import Callable
import fcntl

def _locked_read_modify_write(self, key: str, value: str, modifier_func: Callable):
    with open(self.lock_file, "r+") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            # Atomic swap ensures data integrity
            temp_file.replace(target)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
```