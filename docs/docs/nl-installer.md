# Natural Language Installer (NL Installer)

Cortex supports installing software using natural language instead of
explicit package names.

Example:
```bash
cortex install "something for machine learning"
```
The request is converted into shell commands using the CommandInterpreter
By default, commands are generated and printed (dry-run).
Execution only happens when `--execute` is explicitly provided.

```bash
cortex install "something for machine learning" --execute
```

The NL installer is validated using unit tests in `tests/test_nl_installer.py`.