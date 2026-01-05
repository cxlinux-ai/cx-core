import sys

def generate_systemd_service(name, description, exec_start, user="root"):
    service_content = f"""[Unit]
Description={description}
After=network.target

[Service]
Type=simple
User={user}
ExecStart={exec_start}
Restart=always

[Install]
WantedBy=multi-user.target
"""
    return service_content

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: systemd_helper <name> <description> <exec_command>")
        sys.exit(1)
    
    name, desc, cmd = sys.argv[1], sys.argv[2], sys.argv[3]
    content = generate_systemd_service(name, desc, cmd)
    print(content)
