# Cortex Linux Branding Guide

This document describes the branding assets and visual identity for Cortex Linux.

## Brand Identity

**Name**: Cortex Linux  
**Tagline**: AI-Native Linux Distribution  
**Website**: https://cortexlinux.com  
**Publisher**: AI Venture Holdings LLC

## Color Scheme

The Cortex Linux brand uses a modern, professional color palette:

### Primary Colors
- **Teal**: `#11BFA6` - Primary brand color
- **Mint**: `#69E6D3` - Accent color
- **Background**: `#0B1220` - Dark background
- **Panel**: `#121A2A` - Panel/surface color

### Secondary Colors
- **Success**: `#22C55E` - Success states
- **Danger**: `#EF4444` - Error/warning states
- **Text**: `#FFFFFF` - Primary text
- **Muted Text**: `#AAAAAA` - Secondary text

## Visual Assets

### Logo

The Cortex Linux logo should be used consistently across all materials.

**Usage Guidelines**:
- Minimum size: 32x32 pixels
- Maintain aspect ratio
- Use on light or dark backgrounds with sufficient contrast
- Do not stretch or distort

### Typography

**Primary Font**: System default monospace (for terminal/CLI)
**Secondary Font**: System default sans-serif (for documentation/web)

## Branding Implementation

### Boot Splash (Plymouth)

Cortex Linux uses Plymouth for boot splash screens. The Plymouth theme displays:
- Cortex Linux logo
- Boot progress indicator
- Branded color scheme

**Location**: `/usr/share/plymouth/themes/cortex/`

### MOTD (Message of the Day)

The login banner displays ASCII art and welcome message:

```
   ____          _             _     _                  
  / ___|___  _ _| |_ _____  __| |   (_)_ __  _   ___  __
 | |   / _ \| '__| __/ _ \ \/ /| |   | | '_ \| | | \ \/ /
 | |__| (_) | |  | ||  __/>  < | |___| | | | | |_| |>  < 
  \____\___/|_|   \__\___/_/\_\|_____|_|_| |_|\__,_/_/\_\
                                                        
  AI-Native Linux Distribution
  https://cortexlinux.com
```

**Location**: `/etc/motd`

### Wallpapers

Cortex Linux includes branded wallpapers for desktop environments.

**Specifications**:
- Resolution: 1920x1080 (Full HD), 3840x2160 (4K)
- Format: PNG (with transparency support)
- Style: Minimal, modern, professional

**Location**: `/usr/share/backgrounds/cortex/`

### ISO Branding

ISO images are branded with:
- Cortex Linux name and logo
- Version information
- Publisher information (AI Venture Holdings LLC)
- Website URL

**Config Location**: `iso/live-build/auto/config`

## Branding Files

This repository includes branding assets:

- `branding/plymouth/` - Plymouth boot splash theme
- `branding/wallpapers/` - Desktop wallpapers
- `branding/logos/` - Logo files (SVG, PNG)
- `branding/icons/` - Icon sets

## Implementation Status

- [x] ASCII MOTD
- [x] ISO metadata
- [ ] Plymouth boot splash theme
- [ ] Desktop wallpapers
- [ ] Logo assets (SVG/PNG)
- [ ] Icon sets
- [ ] Documentation styling

## Contributing Branding Assets

When contributing branding assets:

1. Follow the color scheme and style guidelines
2. Ensure assets are scalable (SVG preferred for logos)
3. Include multiple resolutions where applicable
4. Test on both light and dark backgrounds
5. Maintain consistent visual style

## License

All branding assets are copyrighted by AI Venture Holdings LLC and licensed under the same license as Cortex Linux (Apache 2.0).
