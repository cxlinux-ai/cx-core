import re


def fix_line_indent(line):
    """Исправляет отступы в одной строке."""
    # Заменяем все табы на 4 пробела
    line = line.replace("\t", "    ")

    # Считаем ведущие пробелы
    original = line
    stripped = line.lstrip()
    leading_spaces = len(line) - len(stripped)

    # Нормализуем отступ (кратно 4)
    if leading_spaces > 0:
        # Вычисляем уровень отступа
        indent_level = leading_spaces // 4
        # Создаем новый отступ
        new_indent = "    " * indent_level
        return new_indent + stripped
    else:
        return stripped


with open("cortex/permissions/auditor_fixer.py") as f:
    content = f.read()

# Разбиваем на строки
lines = content.split("\n")
fixed_lines = []

for line in lines:
    fixed_line = fix_line_indent(line)
    fixed_lines.append(fixed_line)

# Собираем обратно
fixed_content = "\n".join(fixed_lines)

# Сохраняем
with open("cortex/permissions/auditor_fixer.py", "w") as f:
    f.write(fixed_content)

print(f"Fixed {len(lines)} lines")
