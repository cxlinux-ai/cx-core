import sys

with open("cortex/cli.py") as f:
    lines = f.readlines()

# Находим строку с импортом PermissionManager
for i, line in enumerate(lines):
    if "from cortex.permissions import PermissionManager" in line:
        # Заменяем на правильный импорт
        lines[i] = "from cortex.permissions.auditor_fixer import PermissionAuditor\n"
        # Добавляем алиас на следующей строке
        if i + 1 < len(lines):
            lines.insert(
                i + 1, "PermissionManager = PermissionAuditor  # Alias for compatibility\n"
            )
        break

with open("cortex/cli.py", "w") as f:
    f.writelines(lines)

print("Fixed cli.py import")
