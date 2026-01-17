# Cortex Linux Onboarding Guide

Welcome to Cortex Linux! This guide will help you get started with your new AI-native operating system.

## What is Cortex Linux?

Cortex Linux is an AI-powered Linux distribution that translates natural language commands into Linux operations, making server management intuitive and accessible.

## Quick Start

### 1. Installation

Cortex Linux supports automated installation via preseed for server deployments.

#### Boot from ISO

1. Download the latest Cortex Linux ISO from [cortexlinux.com](https://cortexlinux.com)
2. Create a bootable USB drive or burn to DVD
3. Boot your system from the media

#### Automated Installation

For unattended installation, use the preseed file:

```bash
# Boot with preseed parameter
preseed/file=/cdrom/preseed/cortex.preseed
```

Or via network:
```bash
preseed/url=https://cortexlinux.com/preseed/cortex.preseed
```

#### Manual Installation

Follow the Debian installer prompts. The installation process is standard Debian with Cortex-specific optimizations.

### 2. First Boot

On first boot, Cortex Linux automatically runs provisioning:

- **Hostname Configuration**: Default hostname is `cortex` (configurable)
- **Network Setup**: Automatic DHCP configuration
- **Timezone**: UTC by default (configurable via `/etc/cortex/provision.yaml`)
- **SSH**: Enabled and configured with secure defaults
- **Admin User**: User `cortex` with sudo access (no password required)
- **Security**: AppArmor enabled, firewall configured
- **Cortex Repository**: APT repository configured and ready

Check provisioning status:
```bash
cat /var/log/cortex/firstboot.log
cat /etc/cortex/.provision-state
```

### 3. Initial Configuration

#### Configure System Settings

Edit `/etc/cortex/provision.yaml` (or use the example template):

```bash
sudo cp /etc/cortex/provision.yaml.example /etc/cortex/provision.yaml
sudo nano /etc/cortex/provision.yaml
```

Key settings:
- `hostname`: System hostname
- `timezone`: Timezone (e.g., `America/New_York`)
- `admin_user`: Admin username
- `ssh_authorized_keys`: SSH public keys for passwordless login
- `security`: Security settings (firewall, AppArmor)

After editing, re-run provisioning:
```bash
sudo /usr/lib/cortex/firstboot.sh
```

#### Set SSH Keys

For secure SSH access, add your public key:

```bash
# Add your public key
echo "ssh-rsa YOUR_PUBLIC_KEY" | sudo tee -a /home/cortex/.ssh/authorized_keys
sudo chown cortex:cortex /home/cortex/.ssh/authorized_keys
sudo chmod 600 /home/cortex/.ssh/authorized_keys
```

Or configure via `provision.yaml`:
```yaml
admin_user: cortex
ssh_authorized_keys:
  - ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABA...
  - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI...
```

#### Change Default Password

**Important**: Change the default admin password on first login:

```bash
passwd cortex
```

### 4. Install Packages

#### Core Installation (Minimal)

```bash
sudo apt-get update
sudo apt-get install -y cortex-core
```

Includes:
- Cortex CLI tools
- Python 3.11+
- SSH server
- Security sandbox (Firejail/AppArmor)
- Basic system tools

#### Full Installation (Recommended)

```bash
sudo apt-get install -y cortex-full
```

Includes everything in `cortex-core` plus:
- Docker and container tools
- Network security (nftables, fail2ban)
- Monitoring (Prometheus node exporter)
- Web server (nginx) and TLS (certbot)
- Modern CLI tools (htop, btop, fzf, ripgrep, bat)

#### GPU Support

For NVIDIA GPUs:
```bash
sudo apt-get install -y cortex-gpu-nvidia
sudo cortex-gpu enable
```

For AMD GPUs:
```bash
sudo apt-get install -y cortex-gpu-amd
sudo cortex-gpu enable
```

### 5. Using Cortex

#### Cortex CLI

Cortex provides natural language package management:

```bash
# Show available commands
cortex --help

# Install packages (AI-powered)
cortex install nginx

# System upgrade
cortex upgrade

# GPU management
cortex gpu detect
cortex gpu enable

# System verification
cortex verify
```

#### System Status

Check system status:
```bash
cortex status
```

View logs:
```bash
# First boot provisioning log
cat /var/log/cortex/firstboot.log

# System logs
journalctl -u cortex-firstboot.service
```

### 6. Security Best Practices

#### 1. Change Default Passwords
```bash
passwd cortex
```

#### 2. Configure SSH Keys
Disable password authentication and use SSH keys only (see SSH Keys section above).

#### 3. Enable Automatic Security Updates
```bash
sudo apt-get install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

#### 4. Review Firewall Rules
```bash
sudo nft list ruleset
```

Default firewall policy: DROP (only SSH and configured services allowed).

#### 5. Configure AppArmor
```bash
sudo aa-status
```

#### 6. Regular Updates
```bash
sudo apt-get update
sudo apt-get upgrade
sudo cortex upgrade  # Recommended: uses Cortex upgrade orchestration
```

### 7. Network Configuration

#### Static IP Configuration

Edit `/etc/netplan/01-netcfg.yaml`:

```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      addresses:
        - 192.168.1.100/24
      gateway4: 192.168.1.1
      nameservers:
        addresses:
          - 8.8.8.8
          - 8.8.4.4
```

Apply changes:
```bash
sudo netplan apply
```

### 8. Troubleshooting

#### Provisioning Issues

Check provisioning logs:
```bash
sudo cat /var/log/cortex/firstboot.log
sudo systemctl status cortex-firstboot.service
```

Re-run provisioning manually:
```bash
sudo /usr/lib/cortex/firstboot.sh
```

#### Network Issues

Check network connectivity:
```bash
ping -c 3 8.8.8.8
ip addr show
systemctl status systemd-networkd
```

#### APT Repository Issues

Verify Cortex repository:
```bash
cat /etc/apt/sources.list.d/cortex.sources
apt-key list | grep Cortex
sudo apt-get update
```

#### Boot Issues

Check boot logs:
```bash
journalctl -b
dmesg | less
```

### 9. Getting Help

- **Documentation**: https://cortexlinux.com/docs
- **GitHub**: https://github.com/cortexlinux/cortex-distro
- **Issues**: https://github.com/cortexlinux/cortex-distro/issues
- **Discord**: https://discord.gg/cortexlinux

### 10. Next Steps

- Configure monitoring (Prometheus/Grafana)
- Set up containers (Docker/Podman)
- Deploy applications
- Configure backups
- Review security settings
- Explore Cortex AI features

---

**Welcome to Cortex Linux!** 🚀

For detailed technical documentation, see:
- [Hardware Compatibility](HARDWARE-COMPATIBILITY.md)
- [Key Management](KEY-MANAGEMENT-RUNBOOK.md)
- [Key Rotation](KEY-ROTATION-RUNBOOK.md)
