# Cortex Linux Installation Guide

This guide covers installing Cortex Linux on your system.

## System Requirements

### Minimum Requirements
- **Architecture**: x86_64 (amd64)
- **RAM**: 2GB (4GB recommended)
- **Storage**: 20GB (50GB recommended)
- **Boot**: UEFI or Legacy BIOS

### Supported Hardware
- Standard x86_64 servers and workstations
- Virtual machines (VMware, VirtualBox, KVM, QEMU)
- Cloud platforms (AWS, Azure, GCP, DigitalOcean)
- Raspberry Pi (ARM builds coming soon)

See [Hardware Compatibility](HARDWARE-COMPATIBILITY.md) for detailed compatibility information.

## Downloading Cortex Linux

### Latest Release

Download the latest ISO from:
- **Website**: https://cortexlinux.com/download
- **GitHub Releases**: https://github.com/cortexlinux/cortex-distro/releases

### ISO Variants

1. **Offline ISO** (`cortex-linux-*-offline.iso`)
   - Full offline installation (~2-4GB)
   - Includes all packages
   - No internet connection required
   - Recommended for servers without reliable internet

2. **Network Installer** (`cortex-linux-*-netinst.iso`)
   - Minimal installer (~500MB)
   - Downloads packages during installation
   - Requires internet connection
   - Faster download, longer installation

### Verifying Downloads

Check SHA256 checksums:
```bash
sha256sum -c cortex-linux-*.iso.sha256
```

Or verify against published checksums on the website.

## Creating Installation Media

### USB Drive (Recommended)

#### Linux/macOS
```bash
# Find USB device
lsblk

# Write ISO (replace /dev/sdX with your USB device)
sudo dd if=cortex-linux-0.1.0-amd64-offline.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

#### Windows
Use [Rufus](https://rufus.ie/) or [Balena Etcher](https://www.balena.io/etcher/):
1. Download Rufus or Balena Etcher
2. Select the Cortex Linux ISO
3. Select your USB drive
4. Click "Start" or "Flash"

### DVD/CD
Burn the ISO to a DVD using your preferred burning software (e.g., Brasero, K3b, ImgBurn).

## Installation Methods

### Method 1: Automated Installation (Unattended)

Best for server deployments and automation.

#### Preseed Configuration

1. Boot from ISO with preseed parameter:
   ```bash
   preseed/file=/cdrom/preseed/cortex.preseed
   ```

2. Or use network preseed:
   ```bash
   preseed/url=https://cortexlinux.com/preseed/cortex.preseed
   ```

3. Customize preseed (optional):
   - Edit preseed file before creating ISO
   - Or provide custom preseed URL

#### Preseed Options

The default preseed configuration:
- **Language**: English (US)
- **Keyboard**: US layout
- **Network**: DHCP auto-configuration
- **Partitioning**: LVM with automatic partitioning
- **Boot**: UEFI or BIOS auto-detected
- **User**: Creates `cortex` user with sudo
- **Root**: Root login disabled (use sudo)
- **Packages**: Minimal installation (add `cortex-full` post-install)

### Method 2: Interactive Installation

Best for custom configurations.

1. Boot from installation media
2. Select "Install" from boot menu
3. Follow Debian installer prompts:
   - Language and location
   - Keyboard layout
   - Hostname
   - Network configuration
   - Partitioning (manual or guided)
   - User account setup
   - Software selection
   - Bootloader installation

The installer is standard Debian with Cortex optimizations.

### Method 3: Cloud Installation

#### AWS EC2

1. Create custom AMI from ISO (convert ISO to AMI)
2. Launch EC2 instance from AMI
3. Configure via cloud-init or user-data

#### DigitalOcean

1. Upload ISO via Image Upload API
2. Create Droplet from custom image
3. Configure via user-data script

#### Generic Cloud

1. Boot from ISO in cloud VM
2. Use preseed for automated installation
3. Configure via cloud-init post-installation

## Installation Steps

### Step 1: Boot from Media

1. Insert USB drive or DVD
2. Boot system and enter boot menu (usually F12, F2, or ESC)
3. Select installation media
4. Wait for boot menu

### Step 2: Boot Menu Options

- **Install**: Start interactive installation
- **Graphical Install**: GUI installer (if available)
- **Automated Install**: Use preseed for unattended install
- **Rescue Mode**: Recovery and troubleshooting
- **Memory Test**: Test RAM

### Step 3: Installation Process

#### Partitioning

**Guided (Recommended)**:
- Automatic LVM partitioning
- Separate `/boot`, swap, and root
- Encryption option (LUKS)

**Manual**:
- Full control over partition layout
- Custom mount points
- Multiple disks/RAID support

**Recommended Layout**:
```
/boot   512MB    ext4
swap    2-4GB    (RAM size)
/       Remaining    ext4 (or btrfs for snapshots)
```

#### Software Selection

Installation profiles:
- **Cortex Core** (minimal): Basic system with Cortex CLI
- **Cortex Full** (recommended): Full server environment
- **Custom**: Select individual packages

You can change this post-installation:
```bash
sudo apt-get install cortex-core    # Minimal
sudo apt-get install cortex-full    # Full
```

### Step 4: User Setup

#### Admin User
- Username: `cortex` (default, customizable)
- Password: Set during installation
- Sudo: Enabled automatically

**Security Note**: Change password on first login!

#### SSH Keys
Add SSH public keys during installation (preseed) or post-installation:
```bash
mkdir -p ~/.ssh
echo "ssh-rsa YOUR_KEY" >> ~/.ssh/authorized_keys
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

### Step 5: Finalize Installation

1. Install bootloader (GRUB)
2. Complete installation
3. Reboot into new system

## Post-Installation

### First Boot

On first boot, Cortex Linux automatically:
1. Runs first-boot provisioning
2. Configures network
3. Sets up SSH
4. Applies security settings
5. Configures repositories

Check status:
```bash
sudo systemctl status cortex-firstboot.service
sudo cat /var/log/cortex/firstboot.log
```

### Initial Configuration

1. **Change Password**:
   ```bash
   passwd cortex
   ```

2. **Configure System**:
   ```bash
   sudo cp /etc/cortex/provision.yaml.example /etc/cortex/provision.yaml
   sudo nano /etc/cortex/provision.yaml
   ```

3. **Update System**:
   ```bash
   sudo apt-get update
   sudo apt-get upgrade
   ```

4. **Install Additional Packages**:
   ```bash
   sudo apt-get install cortex-full    # Full installation
   sudo apt-get install cortex-gpu-nvidia    # NVIDIA GPU support
   ```

### Verification

Verify installation:
```bash
# System info
hostnamectl
uname -a

# Cortex CLI
cortex --help

# Network
ip addr show
ping -c 3 8.8.8.8

# Repository
apt policy cortex-core
```

## Troubleshooting

### Boot Issues

**System won't boot from media**:
- Check boot order in BIOS/UEFI
- Enable USB boot in BIOS
- Try different USB port
- Verify ISO checksum

**Boot menu doesn't appear**:
- Media may be corrupted, recreate it
- Try different boot option (UEFI vs Legacy)

### Installation Issues

**Partitioning fails**:
- Check disk for errors: `badblocks -v /dev/sdX`
- Ensure sufficient free space
- Try manual partitioning

**Network not detected**:
- Check cable connections
- Verify network adapter in supported hardware list
- Try manual network configuration

**Package installation fails**:
- Check internet connection (for netinst)
- Verify repository accessibility
- Check disk space: `df -h`

### Post-Installation Issues

**Can't log in**:
- Verify username (default: `cortex`)
- Reset password: boot to recovery mode
- Check provisioning logs: `sudo cat /var/log/cortex/firstboot.log`

**Network not working**:
- Check network config: `ip addr show`
- Restart network: `sudo systemctl restart systemd-networkd`
- Verify DHCP or configure static IP

**SSH not accessible**:
- Check SSH service: `sudo systemctl status ssh`
- Verify firewall: `sudo nft list ruleset`
- Check SSH config: `cat /etc/ssh/sshd_config.d/cortex.conf`

## Advanced Installation

### Preseed Customization

Create custom preseed file:
```bash
# Copy default preseed
cp iso/preseed/cortex.preseed iso/preseed/custom.preseed

# Edit to customize
nano iso/preseed/custom.preseed

# Rebuild ISO with custom preseed
make iso
```

### Network Installation

For network-based installation:
1. Set up PXE server
2. Configure TFTP server
3. Serve preseed and installation files
4. Boot from network

### Automated Deployments

For large-scale deployments:
- Use preseed for automation
- Configure via cloud-init/user-data
- Use infrastructure as code (Terraform, Ansible)
- Automate post-installation configuration

## Getting Help

- **Documentation**: https://cortexlinux.com/docs
- **Onboarding Guide**: [ONBOARDING.md](ONBOARDING.md)
- **GitHub Issues**: https://github.com/cortexlinux/cortex-distro/issues
- **Discord**: https://discord.gg/cortexlinux

---

**Next Steps**: After installation, see the [Onboarding Guide](ONBOARDING.md) to configure and use Cortex Linux.
