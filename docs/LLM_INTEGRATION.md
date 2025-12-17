# LLM Integration Layer - Summary

## Overview
This module provides a Python-based LLM integration layer that converts natural language commands into validated, executable bash commands for Linux systems.

## Features
- **Multi-Provider Support**: Compatible with both OpenAI GPT-4 and Anthropic Claude APIs
- **Natural Language Processing**: Converts user intent into executable system commands
- **Command Validation**: Built-in safety mechanisms to prevent destructive operations
- **Flexible API**: Simple interface with context-aware parsing capabilities
- **Comprehensive Testing**: Unit test suite with 80%+ coverage

## Architecture

### Core Components
1. **CommandInterpreter**: Main class handling LLM interactions and command generation
2. **APIProvider**: Enum for supported LLM providers (OpenAI, Claude)
3. **Validation Layer**: Safety checks for dangerous command patterns

### Key Methods
- `parse(user_input, validate)`: Convert natural language to bash commands
- `parse_with_context(user_input, system_info, validate)`: Context-aware command generation
- `_validate_commands(commands)`: Filter dangerous command patterns
- `_call_openai(user_input)`: OpenAI API integration
- `_call_claude(user_input)`: Claude API integration

## Usage Examples

### Basic Usage
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
