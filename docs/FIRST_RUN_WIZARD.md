# First-Run Wizard Module

**Issue:** #256  
**Status:** Ready for Review  
**Bounty:** As specified in issue (+ bonus after funding)

## Overview

A seamless onboarding experience for new Cortex users. The wizard guides users through API setup, hardware detection, preference configuration, and shell integration in a friendly, step-by-step process.

## Features

### Interactive Setup Flow

1. **Welcome** - Introduction to Cortex
2. **API Configuration** - Set up Claude, OpenAI, or Ollama
3. **Hardware Detection** - Detect GPU, RAM, storage
4. **Preferences** - Configure behavior settings
5. **Shell Integration** - Tab completion and shortcuts
6. **Test Command** - Verify everything works

### Smart Defaults

- Auto-detects existing API keys
- Sensible defaults for all preferences
- Non-interactive mode for automation
- Resume capability if interrupted

### Multiple API Providers

| Provider | Setup | Notes |
|----------|-------|-------|
| Claude (Anthropic) | API key | Recommended |
| OpenAI | API key | Alternative |
| Ollama | Local install | Free, offline |
| None | Skip | Basic apt only |

## Installation

The wizard runs automatically on first use:

```bash
cortex install anything
# → First-run wizard starts automatically
```

Or run manually:

```bash
cortex setup
# or
python -m cortex.first_run_wizard
```

## Usage

### Automatic First Run

```python
from cortex.first_run_wizard import needs_first_run, run_wizard

# Check if setup needed
if needs_first_run():
    success = run_wizard()
    if not success:
        print("Setup cancelled or failed")
```

### Non-Interactive Mode

```python
from cortex.first_run_wizard import run_wizard

# For automation/CI
success = run_wizard(interactive=False)
```

### Access Configuration

```python
from cortex.first_run_wizard import get_config

config = get_config()
print(f"API Provider: {config.get('api_provider')}")
print(f"Preferences: {config.get('preferences')}")
```

### Custom Wizard Instance

```python
from cortex.first_run_wizard import FirstRunWizard
from pathlib import Path

wizard = FirstRunWizard(interactive=True)

# Customize paths (optional)
wizard.CONFIG_DIR = Path("/custom/config")
wizard.CONFIG_FILE = wizard.CONFIG_DIR / "config.json"

# Run wizard
wizard.run()
```

## Wizard Steps

### Step 1: Welcome

Introduces Cortex and explains what it does:
- Natural language package management
- AI-powered command understanding
- Safe execution with rollback

### Step 2: API Configuration

Sets up the AI backend:

**Claude (Recommended):**
```
1. Go to https://console.anthropic.com
2. Create an API key
3. Enter key in wizard
```

**OpenAI:**
```
1. Go to https://platform.openai.com
2. Create an API key
3. Enter key in wizard
```

**Ollama (Local):**
```
1. Install Ollama
2. Pull llama3.2 model
3. No API key needed
```

### Step 3: Hardware Detection

Automatically detects:
- CPU model and cores
- RAM amount
- GPU vendor and model
- Available disk space

Special handling for:
- NVIDIA GPUs (CUDA setup option)
- AMD GPUs (ROCm info)
- Intel GPUs (oneAPI info)

### Step 4: Preferences

Configures:

| Setting | Options | Default |
|---------|---------|---------|
| Auto-confirm | Yes/No | No |
| Verbosity | Quiet/Normal/Verbose | Normal |
| Caching | Enable/Disable | Enabled |

### Step 5: Shell Integration

Sets up:
- Tab completion for `cortex` command
- Supported shells: bash, zsh, fish
- Optional keyboard shortcuts

### Step 6: Test Command

Runs a simple test to verify setup:
```bash
cortex search text editors
```

## API Reference

### FirstRunWizard

Main wizard class.

**Constructor:**
```python
FirstRunWizard(interactive: bool = True)
```

**Methods:**

| Method | Description |
|--------|-------------|
| `needs_setup()` | Check if first-run is needed |
| `run()` | Run the complete wizard |
| `load_state()` | Load saved wizard state |
| `save_state()` | Save current wizard state |
| `save_config()` | Save configuration |
| `mark_setup_complete()` | Mark setup as finished |

### WizardState

Tracks wizard progress.

```python
@dataclass
class WizardState:
    current_step: WizardStep
    completed_steps: List[WizardStep]
    skipped_steps: List[WizardStep]
    collected_data: Dict[str, Any]
    started_at: datetime
    completed_at: Optional[datetime]
```

### WizardStep

Enum of wizard steps:

```python
class WizardStep(Enum):
    WELCOME = "welcome"
    API_SETUP = "api_setup"
    HARDWARE_DETECTION = "hardware_detection"
    PREFERENCES = "preferences"
    SHELL_INTEGRATION = "shell_integration"
    TEST_COMMAND = "test_command"
    COMPLETE = "complete"
```

### StepResult

Result of each step:

```python
@dataclass
class StepResult:
    success: bool
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    next_step: Optional[WizardStep] = None
    skip_to: Optional[WizardStep] = None
```

## Configuration Files

### Location

All files stored in `~/.cortex/`:

| File | Purpose |
|------|---------|
| `config.json` | User configuration |
| `wizard_state.json` | Wizard progress |
| `.setup_complete` | Setup completion marker |
| `completion.bash` | Shell completion |

### Config Format

```json
{
  "api_provider": "anthropic",
  "api_key_configured": true,
  "hardware": {
    "cpu": "Intel Core i7-9700K",
    "ram_gb": 32,
    "gpu": "NVIDIA GeForce RTX 4090",
    "gpu_vendor": "nvidia",
    "disk_gb": 500
  },
  "preferences": {
    "auto_confirm": false,
    "verbosity": "normal",
    "enable_cache": true
  }
}
```

## CLI Integration

### In Main CLI

```python
# In cortex/cli.py
from cortex.first_run_wizard import needs_first_run, run_wizard

@cli.callback()
def main():
    if needs_first_run():
        if not run_wizard():
            raise SystemExit("Setup required")

@cli.command()
def setup(force: bool = False):
    """Run setup wizard."""
    if force or needs_first_run():
        run_wizard()
    else:
        print("Already set up. Use --force to run again.")
```

### As Standalone

```bash
# Run wizard directly
python -m cortex.first_run_wizard

# Force re-run
python -m cortex.first_run_wizard --force
```

## Shell Completion

### Bash

Added to `~/.bashrc`:
```bash
# Cortex completion
[ -f ~/.cortex/completion.bash ] && source ~/.cortex/completion.bash
```

### Zsh

Added to `~/.zshrc`:
```bash
# Cortex completion
[ -f ~/.cortex/completion.zsh ] && source ~/.cortex/completion.zsh
```

### Fish

Added to `~/.config/fish/config.fish`:
```fish
# Cortex completion
source ~/.cortex/completion.fish
```

## Testing

```bash
# Run all tests
pytest tests/test_first_run_wizard.py -v

# Run with coverage
pytest tests/test_first_run_wizard.py --cov=cortex.first_run_wizard

# Test specific functionality
pytest tests/test_first_run_wizard.py -k "api_setup" -v
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   FirstRunWizard                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │
│  │ WizardState │  │  StepResult │  │ Step Handlers   │ │
│  └─────────────┘  └─────────────┘  └─────────────────┘ │
└────────────────────────┬────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   Config    │  │    State    │  │    Shell    │
│    File     │  │    File     │  │   Config    │
└─────────────┘  └─────────────┘  └─────────────┘
```

## Troubleshooting

### Wizard Won't Start

```python
from cortex.first_run_wizard import FirstRunWizard

wizard = FirstRunWizard()
print(f"Setup complete file: {wizard.SETUP_COMPLETE_FILE}")
print(f"Exists: {wizard.SETUP_COMPLETE_FILE.exists()}")

# Remove to re-run
wizard.SETUP_COMPLETE_FILE.unlink()
```

### API Key Not Saved

```bash
# Check if key is in environment
echo $ANTHROPIC_API_KEY

# Check shell config
grep ANTHROPIC ~/.bashrc ~/.zshrc

# Restart shell or source config
source ~/.bashrc
```

### Shell Completion Not Working

```bash
# Check if completion file exists
ls -la ~/.cortex/completion.*

# Source manually
source ~/.cortex/completion.bash

# Check for errors
bash -x ~/.cortex/completion.bash
```

### Resume Interrupted Wizard

```python
from cortex.first_run_wizard import FirstRunWizard

wizard = FirstRunWizard()
wizard.load_state()

print(f"Current step: {wizard.state.current_step}")
print(f"Completed: {wizard.state.completed_steps}")

# Continue from where left off
wizard.run()
```

## Contributing

1. Add new steps to `WizardStep` enum
2. Create step handler method `_step_<name>`
3. Add to steps list in `run()`
4. Add tests for new functionality
5. Update documentation

---

**Closes:** #256
