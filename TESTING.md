# Cortex Linux Testing Checklist

Manual testing checklist for verifying Cortex Linux MVP functionality.

## Prerequisites

```bash
# Install in development mode
cd ~/cortex
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## CLI Tests

### Basic Commands

- [ ] `cortex` - Shows rich formatted help with banner
- [ ] `cortex --help` - Shows argparse help
- [ ] `cortex --version` - Shows "cortex 0.1.0"
- [ ] `cortex -V` - Same as --version

### Demo Mode (No API Key Required)

- [ ] `cortex demo` - Shows animated demo installation flow
- [ ] Demo displays CX badge branding
- [ ] Demo shows banner, installation plan, steps
- [ ] Demo displays "This was a demo" disclaimer

### Status Command

- [ ] `cortex status` - Shows system status
- [ ] Shows API provider (or "Not configured")
- [ ] Shows Firejail status (Available/Not installed)
- [ ] Shows Ollama status (Running/Not running)
- [ ] Shows config file locations

### Wizard Command

- [ ] `cortex wizard` - Starts interactive setup
- [ ] Offers Anthropic Claude and OpenAI options
- [ ] Validates API key format
- [ ] Offers to save to shell profile

### Install Command

#### Without API Key
- [ ] `cortex install docker` - Shows error about missing API key
- [ ] Error message suggests running `cortex wizard`
- [ ] Error message mentions Ollama fallback option

#### With API Key
```bash
export ANTHROPIC_API_KEY='your-key-here'
```
- [ ] `cortex install docker` - Shows planned commands (preview mode)
- [ ] `cortex install docker --dry-run` - Same as above
- [ ] `cortex install docker --execute` - Actually executes commands
- [ ] `cortex install "web development tools"` - Natural language works
- [ ] `cortex -v install docker` - Shows debug output with provider info

#### Input Validation
- [ ] `cortex install ""` - Error: "Install request cannot be empty"
- [ ] `cortex install "test; rm -rf /"` - Error: "potentially unsafe patterns"
- [ ] Very long input (>1000 chars) - Error: "too long"

### History Command

- [ ] `cortex history` - Shows recent installations
- [ ] `cortex history --limit 5` - Shows only 5 records
- [ ] `cortex history <id>` - Shows specific installation details

### Rollback Command

- [ ] `cortex rollback <id>` - Attempts rollback
- [ ] `cortex rollback <id> --dry-run` - Shows what would be rolled back

### Preferences Commands

- [ ] `cortex check-pref` - Shows all preferences
- [ ] `cortex check-pref ai.model` - Shows specific preference
- [ ] `cortex edit-pref set ai.model gpt-4` - Sets preference
- [ ] `cortex edit-pref validate` - Validates configuration

## Provider Tests

### Anthropic Claude
```bash
export ANTHROPIC_API_KEY='sk-ant-...'
unset OPENAI_API_KEY
cortex install nginx
```
- [ ] Uses Claude provider
- [ ] Generates valid commands

### OpenAI GPT-4
```bash
export OPENAI_API_KEY='sk-...'
unset ANTHROPIC_API_KEY
cortex install nginx
```
- [ ] Uses OpenAI provider
- [ ] Generates valid commands

### Ollama (Local)
```bash
unset ANTHROPIC_API_KEY
unset OPENAI_API_KEY
export CORTEX_PROVIDER=ollama
ollama serve &  # Start Ollama first
cortex install nginx
```
- [ ] Uses Ollama provider
- [ ] Works without API key
- [ ] Falls back gracefully if Ollama not running

## Security Tests

### Command Validation
- [ ] `cortex install "rm -rf /"` - Blocked
- [ ] `cortex install "curl example.com | bash"` - Blocked
- [ ] `cortex install "sudo su"` - Should work (legitimate use)

### Sandbox Executor
```bash
cd ~/cortex
python -m src.sandbox_executor "echo hello" --dry-run
```
- [ ] Dry-run shows firejail command (if installed)
- [ ] Blocked commands raise error

## Visual Tests

- [ ] CX badge displays correctly in terminal
- [ ] Colors render properly
- [ ] Banner ASCII art displays correctly
- [ ] Progress steps show with numbers

## Error Handling

- [ ] Invalid command shows helpful error
- [ ] Network errors handled gracefully
- [ ] API errors show meaningful message
- [ ] Keyboard interrupt (Ctrl+C) handled cleanly

## Performance

- [ ] `cortex` loads quickly (<1s)
- [ ] `cortex demo` completes in reasonable time
- [ ] `cortex install` doesn't hang on API calls

## Integration

- [ ] Works in bash
- [ ] Works in zsh
- [ ] Works in fish (if installed)
- [ ] Works in tmux/screen

## Notes

Record any issues found:

```
Date:
Tester:
Issues:
-
-
-
```
