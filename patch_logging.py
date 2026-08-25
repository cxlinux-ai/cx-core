with open('cx/system_alert_manager.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if line.strip() == '# Configure enterprise logging':
        indent = line[:len(line) - len(line.lstrip())]
        insert = [
            f"{indent}# Ensure log directory exists before creating FileHandler\n",
            f"{indent}Path.home().joinpath(\".cx\").mkdir(parents=True, exist_ok=True, mode=0o700)\n",
            "\n"
        ]
        lines = lines[:i] + insert + lines[i:]
        break

with open('cx/system_alert_manager.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Patched cx/system_alert_manager.py')
