# Cortex Linux MCP Server

Connect any MCP-compatible AI (Claude, ChatGPT, Cursor, VS Code) to Cortex Linux.

## Install

```bash
pip install cortex-mcp-server
```

## Configure Claude Desktop

Add to `~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cortex-linux": {
      "command": "cortex-mcp-server"
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| install_package | Install packages via natural language |
| search_packages | Search package database |
| get_history | View installation history |
| rollback | Rollback previous installation |
| detect_hardware | Detect GPU/CPU |
| system_status | Get system status |

## Safety

- Dry-run by default
- Explicit confirmation required for changes
- Firejail sandboxing
- Full audit logging

## Links

- [MCP Specification](https://modelcontextprotocol.io)
- [AAIF](https://aaif.io)
- [Discord](https://discord.gg/uCqHvxjU83)
