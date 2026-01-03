# Approval Modes

## Overview

Cortex supports **tiered approval modes** that control how and when system actions
(such as shell commands) are executed.  
This feature improves safety, transparency, and flexibility for different workflows.

Approval mode is a **persistent user setting** and applies across all Cortex commands.

---

## Available Modes

| Mode | Description | Execution Behavior |
|------|------------|--------------------|
| `suggest` | Plan-only mode | Commands are generated but **never executed** |
| `auto-edit` | Confirmed execution | Commands execute **only after user confirmation** |
| `full-auto` | Fully automatic | Commands execute **without prompts** |

---

## Setting the Approval Mode

Use the CLI to set the approval mode:

```bash
cortex config set approval-mode suggest
cortex config set approval-mode auto-edit
cortex config set approval-mode full-auto
```

commands are executed only when --execute flag is provided

```bash
cortex config set  approval-mode full-auto,cortex install pandas --execute
```