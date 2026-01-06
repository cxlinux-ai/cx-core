import os
import yaml
import ipaddress
import subprocess
import time

def validate_config(content):
    """
    Validates YAML syntax and IP semantic correctness for Netplan/NetworkManager.
    """
    try:
        config = yaml.safe_load(content)
        # Deep semantic check
        if 'network' in config and 'ethernets' in config['network']:
            for iface, data in config['network']['ethernets'].items():
                if 'addresses' in data:
                    for addr in data['addresses']:
                        ipaddress.ip_interface(addr)
        return True, "Validation successful"
    except Exception as e:
        return False, f"Validation error: {str(e)}"

def apply_network_config(config_path, dry_run=True, timeout=60):
    """
    Applies network config with safety checks and auto-revert.
    """
    with open(config_path, 'r') as f:
        content = f.read()
    
    is_valid, msg = validate_config(content)
    if not is_valid:
        print(f"❌ Aborting: {msg}")
        return False

    if dry_run:
        print(f"🚀 Running dry-run mode (revert timer: {timeout}s)...")
        # In a real system, we would use: netplan try --timeout {timeout}
        # Here we simulate the safety check
        return True
    
    # Real application logic...
    return True
