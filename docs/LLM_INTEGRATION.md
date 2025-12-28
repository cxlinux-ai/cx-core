# LLM Integration Layer - Summary

## Overview
This module provides a Python-based LLM integration layer that converts natural language commands into validated, executable bash commands for Linux systems.

## Features
- **Multi-Provider Support**: Compatible with OpenAI GPT-4, Anthropic Claude, and Ollama (local LLMs)
- **Natural Language Processing**: Converts user intent into executable system commands
- **Command Validation**: Built-in safety mechanisms to prevent destructive operations
- **Flexible API**: Simple interface with context-aware parsing capabilities
- **Free Local Option**: Use Ollama for free, offline LLM inference
- **Comprehensive Testing**: Unit test suite with 80%+ coverage

## Supported Providers

| Provider | Type | Cost | Privacy | Offline | Setup |
|----------|------|------|---------|---------|-------|
| **Ollama** | Local | Free | 100% Private | Yes | [Setup Guide](OLLAMA_SETUP.md) |
| **Claude** | Cloud API | Paid | Data sent to cloud | No | API key required |
| **OpenAI** | Cloud API | Paid | Data sent to cloud | No | API key required |
| **Kimi K2** | Cloud API | Paid | Data sent to cloud | No | API key required |

## Architecture

### Core Components
1. **LLMRouter**: Intelligent routing between multiple LLM providers
2. **CommandInterpreter**: Main class handling LLM interactions and command generation
3. **LLMProvider**: Enum for supported LLM providers (Claude, OpenAI, Ollama, Kimi K2)
4. **Validation Layer**: Safety checks for dangerous command patterns

### Key Classes

#### LLMRouter
Routes requests to the most appropriate LLM based on task type:
- User-facing tasks → Claude (better at natural language)
- System operations → Kimi K2 (superior agentic capabilities)
- Local inference → Ollama (free, private)

#### LLMProvider Enum
```python
class LLMProvider(Enum):
    CLAUDE = "claude"
    KIMI_K2 = "kimi_k2"
    OLLAMA = "ollama"
```

### Key Methods
- `parse(user_input, validate)`: Convert natural language to bash commands
- `parse_with_context(user_input, system_info, validate)`: Context-aware command generation
- `_validate_commands(commands)`: Filter dangerous command patterns
- `_call_openai(user_input)`: OpenAI API integration
- `_call_claude(user_input)`: Claude API integration

## Usage Examples

### Using Ollama (Free, Local)
```python
from cortex.llm_router import LLMRouter, LLMProvider

# Initialize with Ollama
router = LLMRouter(
    ollama_base_url="http://localhost:11434",
    ollama_model="llama3.2",
    default_provider=LLMProvider.OLLAMA
)

# Generate response
response = router.complete(
    messages=[{"role": "user", "content": "install nginx"}],
    task_type=TaskType.SYSTEM_OPERATION
)

print(response.content)
# No API costs! All processing happens locally
```

### Basic Usage with Claude
```python
from cortex.llm_router import LLMRouter

router = LLMRouter(api_key="your-api-key", provider="claude")
commands = router.parse("install docker with nvidia support")
# Returns: ["sudo apt update", "sudo apt install -y docker.io", "sudo apt install -y nvidia-docker2", "sudo systemctl restart docker"]
```

### Using Multiple Providers
```python
from cortex.llm_router import LLMRouter, LLMProvider

# Initialize with multiple providers
router = LLMRouter(
    claude_api_key="your-claude-key",
    ollama_base_url="http://localhost:11434",
    ollama_model="llama3.2",
    enable_fallback=True  # Fall back to Ollama if Claude fails
)

# Router automatically selects best provider for task
response = router.complete(
    messages=[{"role": "user", "content": "install nginx"}],
    task_type=TaskType.SYSTEM_OPERATION
)
```

### Basic Usage (Legacy)
```python
from LLM import CommandInterpreter

interpreter = CommandInterpreter(api_key="your-api-key", provider="openai")
commands = interpreter.parse("install docker with nvidia support")
# Returns: ["sudo apt update", "sudo apt install -y docker.io", "sudo apt install -y nvidia-docker2", "sudo systemctl restart docker"]
```

### Claude Provider
```python
interpreter = CommandInterpreter(api_key="your-api-key", provider="claude")
commands = interpreter.parse("update system packages")
```

### Context-Aware Parsing
```python
system_info = {"os": "ubuntu", "version": "22.04"}
commands = interpreter.parse_with_context("install nginx", system_info=system_info)
```

### Custom Model
```python
interpreter = CommandInterpreter(
    api_key="your-api-key",
    provider="openai",
    model="gpt-4-turbo"
)
```

## Installation

```bash
pip install -r requirements.txt
```

## Testing

```bash
python -m unittest test_interpreter.py
```

## Safety Features

The module includes validation to prevent execution of dangerous commands:
- `rm -rf /` patterns
- Disk formatting operations (`mkfs.`, `dd if=`)
- Direct disk writes (`> /dev/sda`)
- Fork bombs

## API Response Format

LLMs are prompted to return responses in structured JSON format:
```json
{
  "commands": ["command1", "command2", "command3"]
}
```

## Error Handling

- **APIError**: Raised when LLM API calls fail
- **ValueError**: Raised for invalid input or unparseable responses
- **ImportError**: Raised when required packages are not installed

## Supported Scenarios

The system handles 20+ common installation and configuration scenarios including:
- Package installation (Docker, Nginx, PostgreSQL, etc.)
- System updates and upgrades
- Service management
- User and permission management
- Network configuration
- File system operations

## Technical Specifications

- **Language**: Python 3.8+
- **Dependencies**: openai>=1.0.0, anthropic>=0.18.0
- **Test Coverage**: 80%+
- **Default Models**: GPT-4 (OpenAI), Claude-3.5-Sonnet (Anthropic)
- **Temperature**: 0.3 (for consistent command generation)
- **Max Tokens**: 1000

## Future Enhancements

- Support for additional LLM providers
- Enhanced command validation with sandboxing
- Command execution monitoring
- Multi-language support for non-bash shells
- Caching layer for common requests
