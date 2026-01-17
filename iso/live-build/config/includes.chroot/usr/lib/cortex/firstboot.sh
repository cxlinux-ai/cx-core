#!/bin/bash
# Cortex Linux First Boot Provisioning
# Runs on first boot to complete system setup
# Copyright 2025 AI Venture Holdings LLC
# SPDX-License-Identifier: Apache-2.0

set -e

PROVISION_VERSION="1.0.0"
PROVISION_LOG="/var/log/cortex/firstboot.log"
STATE_FILE="/etc/cortex/.provision-state"
CONFIG_FILE="/etc/cortex/provision.yaml"

# Logging
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$PROVISION_LOG"
}

log_section() {
    log "=============================================="
    log "$*"
    log "=============================================="
}

# Error handling
error_exit() {
    log "ERROR: $*"
    exit 1
}

# State management for idempotency
state_get() {
    local key="$1"
    if [ -f "$STATE_FILE" ]; then
        grep "^${key}=" "$STATE_FILE" 2>/dev/null | cut -d'=' -f2-
    fi
}

state_set() {
    local key="$1"
    local value="$2"
    mkdir -p "$(dirname "$STATE_FILE")"
    if [ -f "$STATE_FILE" ]; then
        sed -i "/^${key}=/d" "$STATE_FILE"
    fi
    echo "${key}=${value}" >> "$STATE_FILE"
}

state_done() {
    local step="$1"
    state_set "step_${step}" "done"
}

state_check() {
    local step="$1"
    [ "$(state_get "step_${step}")" = "done" ]
}

# =============================================================================
# PROVISIONING STEPS
# =============================================================================

provision_hostname() {
    if state_check "hostname"; then
        log "Hostname already configured, skipping"
        return 0
    fi
    
    log_section "Configuring Hostname"
    
    # Read from provision config or use default
    local hostname="${CORTEX_HOSTNAME:-cortex}"
    
    if [ -f "$CONFIG_FILE" ]; then
        local cfg_hostname
        cfg_hostname=$(grep -E "^hostname:" "$CONFIG_FILE" 2>/dev/null | awk '{print $2}')
        [ -n "$cfg_hostname" ] && hostname="$cfg_hostname"
    fi
    
    hostnamectl set-hostname "$hostname"
    log "Hostname set to: $hostname"
    
    state_done "hostname"
}

provision_network() {
    if state_check "network"; then
        log "Network already configured, skipping"
        return 0
    fi
    
    log_section "Configuring Network"
    
    # Network is typically configured via DHCP during install
    # This step validates connectivity
    
    if ping -c 1 -W 5 8.8.8.8 &>/dev/null; then
        log "Network connectivity verified"
    else
        log "WARNING: No network connectivity detected"
        log "System will operate in offline mode"
    fi
    
    state_done "network"
}

provision_timezone() {
    if state_check "timezone"; then
        log "Timezone already configured, skipping"
        return 0
    fi
    
    log_section "Configuring Timezone"
    
    local timezone="${CORTEX_TIMEZONE:-UTC}"
    
    if [ -f "$CONFIG_FILE" ]; then
        local cfg_tz
        cfg_tz=$(grep -E "^timezone:" "$CONFIG_FILE" 2>/dev/null | awk '{print $2}')
        [ -n "$cfg_tz" ] && timezone="$cfg_tz"
    fi
    
    timedatectl set-timezone "$timezone"
    log "Timezone set to: $timezone"
    
    state_done "timezone"
}

provision_ssh() {
    if state_check "ssh"; then
        log "SSH already configured, skipping"
        return 0
    fi
    
    log_section "Configuring SSH"
    
    # Ensure SSH is enabled
    systemctl enable ssh
    systemctl start ssh
    
    # Generate host keys if missing
    if [ ! -f /etc/ssh/ssh_host_ed25519_key ]; then
        log "Regenerating SSH host keys..."
        rm -f /etc/ssh/ssh_host_*
        dpkg-reconfigure openssh-server
    fi
    
    # Inject authorized keys if provided
    if [ -f "$CONFIG_FILE" ]; then
        local ssh_keys
        ssh_keys=$(grep -E "^ssh_authorized_keys:" -A 100 "$CONFIG_FILE" 2>/dev/null | grep -E "^\s+-" | sed 's/^\s*-\s*//')
        
        if [ -n "$ssh_keys" ]; then
            local admin_user
            admin_user=$(grep -E "^admin_user:" "$CONFIG_FILE" | awk '{print $2}')
            admin_user="${admin_user:-cortex}"
            
            local ssh_dir="/home/${admin_user}/.ssh"
            mkdir -p "$ssh_dir"
            echo "$ssh_keys" >> "${ssh_dir}/authorized_keys"
            chmod 700 "$ssh_dir"
            chmod 600 "${ssh_dir}/authorized_keys"
            chown -R "${admin_user}:${admin_user}" "$ssh_dir"
            
            log "SSH keys installed for user: $admin_user"
            
            # Disable password auth if keys provided
            sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config.d/cortex.conf
            systemctl reload ssh
            log "Password authentication disabled (SSH keys configured)"
        fi
    fi
    
    log "SSH configured and running"
    state_done "ssh"
}

provision_admin_user() {
    if state_check "admin_user"; then
        log "Admin user already configured, skipping"
        return 0
    fi
    
    log_section "Configuring Admin User"
    
    local admin_user="${CORTEX_ADMIN_USER:-cortex}"
    
    if [ -f "$CONFIG_FILE" ]; then
        local cfg_user
        cfg_user=$(grep -E "^admin_user:" "$CONFIG_FILE" 2>/dev/null | awk '{print $2}')
        [ -n "$cfg_user" ] && admin_user="$cfg_user"
    fi
    
    # Create user if doesn't exist
    if ! id "$admin_user" &>/dev/null; then
        useradd -m -s /bin/bash -G sudo,docker "$admin_user"
        log "Created admin user: $admin_user"
    fi
    
    # Ensure sudo access
    echo "${admin_user} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${admin_user}"
    chmod 440 "/etc/sudoers.d/${admin_user}"
    
    log "Admin user configured: $admin_user"
    state_done "admin_user"
}

provision_apt_repos() {
    if state_check "apt_repos"; then
        log "APT repositories already configured, skipping"
        return 0
    fi
    
    log_section "Configuring APT Repositories"
    
    # Update package lists
    apt-get update || log "WARNING: apt-get update failed (offline mode?)"
    
    log "APT repositories configured"
    state_done "apt_repos"
}

provision_cortex() {
    if state_check "cortex"; then
        log "Cortex already installed, skipping"
        return 0
    fi
    
    log_section "Installing Cortex"
    
    # Check if we have network for installation
    if ping -c 1 -W 5 repo.cortexlinux.com &>/dev/null; then
        apt-get install -y cortex-core || log "WARNING: cortex-core installation failed"
    else
        log "No network access to Cortex repository"
        log "Cortex will be installed from local packages if available"
        
        # Check for local packages
        if ls /var/cache/cortex/*.deb &>/dev/null; then
            dpkg -i /var/cache/cortex/*.deb || true
            apt-get install -f -y
        fi
    fi
    
    state_done "cortex"
}

provision_security() {
    if state_check "security"; then
        log "Security baseline already applied, skipping"
        return 0
    fi
    
    log_section "Applying Security Baseline"
    
    # Apply sysctl settings
    sysctl --system
    
    # Enable AppArmor
    if command -v aa-status &>/dev/null; then
        systemctl enable apparmor
        systemctl start apparmor
        log "AppArmor enabled"
    fi
    
    # Configure firewall (nftables)
    if command -v nft &>/dev/null; then
        cat > /etc/nftables.conf << 'EOF'
#!/usr/sbin/nft -f

flush ruleset

table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        
        # Allow established connections
        ct state established,related accept
        
        # Allow loopback
        iif lo accept
        
        # Allow SSH
        tcp dport 22 accept
        
        # Allow Cortex web console (when enabled)
        tcp dport 8006 accept
        
        # Allow ICMP
        icmp type echo-request accept
        icmpv6 type echo-request accept
        
        # Drop invalid
        ct state invalid drop
    }
    
    chain forward {
        type filter hook forward priority 0; policy drop;
    }
    
    chain output {
        type filter hook output priority 0; policy accept;
    }
}
EOF
        systemctl enable nftables
        systemctl start nftables
        log "Firewall configured (nftables)"
    fi
    
    log "Security baseline applied"
    state_done "security"
}

provision_webconsole() {
    if state_check "webconsole"; then
        log "Web console already configured, skipping"
        return 0
    fi
    
    log_section "Configuring Web Console"
    
    # Web console will be configured when cortex-console is installed
    # This step prepares the environment
    
    mkdir -p /etc/cortex/console
    mkdir -p /var/lib/cortex/console
    
    log "Web console environment prepared"
    log "Install cortex-console to enable web management on port 8006"
    
    state_done "webconsole"
}

# =============================================================================
# MAIN
# =============================================================================

show_welcome() {
    cat << 'EOF'

   ____          _             _     _                  
  / ___|___  _ _| |_ _____  __| |   (_)_ __  _   ___  __
 | |   / _ \| '__| __/ _ \ \/ /| |   | | '_ \| | | \ \/ /
 | |__| (_) | |  | ||  __/>  < | |___| | | | | |_| |>  < 
  \____\___/|_|   \__\___/_/\_\|_____|_|_| |_|\__,_/_/\_\
                                                        
  AI-Native Linux Distribution
  https://cortexlinux.com

  Welcome to Cortex Linux!
  
  Your system is being configured for first use.
  This will only take a few moments...

EOF
}

show_completion() {
    local hostname=$(hostname)
    local admin_user="${CORTEX_ADMIN_USER:-cortex}"
    
    cat << EOF

   ____          _             _     _                  
  / ___|___  _ _| |_ _____  __| |   (_)_ __  _   ___  __
 | |   / _ \| '__| __/ _ \ \/ /| |   | | '_ \| | | \ \/ /
 | |__| (_) | |  | ||  __/>  < | |___| | | | | |_| |>  < 
  \____\___/|_|   \__\___/_/\_\|_____|_|_| |_|\__,_/_/\_\
                                                        
  AI-Native Linux Distribution
  https://cortexlinux.com

  ✓ Cortex Linux is ready!

  System Information:
    Hostname: ${hostname}
    Admin User: ${admin_user}
    Provisioning: Complete
  
  Next Steps:
    1. Change default password: passwd ${admin_user}
    2. Configure system: sudo nano /etc/cortex/provision.yaml
    3. Install packages: sudo apt-get install cortex-full
    4. Get help: cortex --help
  
  Documentation: https://cortexlinux.com/docs
  GitHub: https://github.com/cortexlinux/cortex-distro
  Discord: https://discord.gg/cortexlinux

  System is ready. You can connect via SSH or web console (port 8006).

EOF
}

main() {
    # Show welcome message
    show_welcome
    
    log_section "Cortex Linux First Boot Provisioning v${PROVISION_VERSION}"
    log "Started: $(date)"
    
    # Create log directory
    mkdir -p "$(dirname "$PROVISION_LOG")"
    
    # Run provisioning steps in order
    log "Step 1/9: Configuring hostname..."
    provision_hostname
    
    log "Step 2/9: Configuring network..."
    provision_network
    
    log "Step 3/9: Configuring timezone..."
    provision_timezone
    
    log "Step 4/9: Configuring SSH..."
    provision_ssh
    
    log "Step 5/9: Configuring admin user..."
    provision_admin_user
    
    log "Step 6/9: Configuring APT repositories..."
    provision_apt_repos
    
    log "Step 7/9: Installing Cortex..."
    provision_cortex
    
    log "Step 8/9: Applying security baseline..."
    provision_security
    
    log "Step 9/9: Configuring web console..."
    provision_webconsole
    
    # Mark provisioning complete
    state_set "provision_version" "$PROVISION_VERSION"
    state_set "provision_complete" "$(date -Iseconds)"
    
    log_section "Provisioning Complete"
    log "Finished: $(date)"
    
    # Show completion message
    show_completion
    
    # Log to systemd journal
    systemd-cat -t cortex-firstboot -p info echo "Cortex Linux first boot provisioning completed successfully"
}

# Run main function
main "$@"
