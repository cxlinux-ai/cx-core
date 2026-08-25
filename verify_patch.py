with open('cx/system_alert_manager.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines[:80], start=1):
    print(f"{i}: {line}", end='')
