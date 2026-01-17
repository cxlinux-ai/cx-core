#!/bin/bash
# Cortex Linux ISO Verification Tests
# Validates ISO integrity and bootability
# Copyright 2025 AI Venture Holdings LLC
# SPDX-License-Identifier: Apache-2.0

set -e

ISO_FILE="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
SKIP=0

pass() { echo -e "${GREEN}[PASS]${NC} $*"; ((PASS++)); }
fail() { echo -e "${RED}[FAIL]${NC} $*"; ((FAIL++)); }
skip() { echo -e "${YELLOW}[SKIP]${NC} $*"; ((SKIP++)); }
info() { echo -e "[INFO] $*"; }

# Usage check
if [ -z "$ISO_FILE" ]; then
    echo "Usage: $0 <iso-file>"
    exit 1
fi

if [ ! -f "$ISO_FILE" ]; then
    fail "ISO file not found: $ISO_FILE"
    exit 1
fi

info "================================================"
info "Cortex Linux ISO Verification"
info "ISO: $ISO_FILE"
info "================================================"

# Test 1: File exists and is readable
test_file_readable() {
    if [ -r "$ISO_FILE" ]; then
        pass "ISO file is readable"
    else
        fail "ISO file is not readable"
    fi
}

# Test 2: Check file size (should be > 500MB for offline ISO)
test_file_size() {
    local size
    size=$(stat -f%z "$ISO_FILE" 2>/dev/null || stat -c%s "$ISO_FILE" 2>/dev/null)
    
    if [ "$size" -gt 500000000 ]; then
        pass "ISO size is reasonable: $(numfmt --to=iec $size)"
    elif [ "$size" -gt 100000000 ]; then
        pass "ISO size for netinst: $(numfmt --to=iec $size)"
    else
        fail "ISO size too small: $(numfmt --to=iec $size)"
    fi
}

# Test 3: Verify ISO is valid ISO9660/hybrid
test_iso_format() {
    if command -v file &>/dev/null; then
        local file_type
        file_type=$(file "$ISO_FILE")
        
        if echo "$file_type" | grep -qiE "ISO 9660|DOS/MBR boot sector|hybrid"; then
            pass "Valid ISO format: $file_type"
        else
            fail "Invalid ISO format: $file_type"
        fi
    else
        skip "file command not available"
    fi
}

# Test 4: Check ISO contents (mount and verify)
test_iso_contents() {
    if [ "$(id -u)" -ne 0 ]; then
        skip "ISO content check requires root (run with sudo)"
        return
    fi
    
    local mount_point
    mount_point=$(mktemp -d)
    
    if mount -o loop,ro "$ISO_FILE" "$mount_point" 2>/dev/null; then
        # Check for essential files
        local essential_files=(
            "isolinux/isolinux.bin"
            "EFI/BOOT/BOOTX64.EFI"
            "live/vmlinuz"
            "live/initrd.img"
            "live/filesystem.squashfs"
        )
        
        local missing=0
        for f in "${essential_files[@]}"; do
            if [ -f "$mount_point/$f" ]; then
                info "  Found: $f"
            else
                info "  Missing: $f"
                ((missing++))
            fi
        done
        
        umount "$mount_point"
        rmdir "$mount_point"
        
        if [ $missing -eq 0 ]; then
            pass "All essential ISO files present"
        else
            fail "$missing essential files missing"
        fi
    else
        fail "Could not mount ISO"
        rmdir "$mount_point" 2>/dev/null
    fi
}

# Test 5: Verify checksum file if present
test_checksum() {
    local checksum_file="${ISO_FILE}.sha256"
    
    if [ -f "$checksum_file" ]; then
        if sha256sum -c "$checksum_file" &>/dev/null; then
            pass "SHA256 checksum verified"
        else
            fail "SHA256 checksum mismatch"
        fi
    else
        skip "No SHA256 checksum file found"
    fi
}

# Test 6: Check UEFI bootability
test_uefi_boot() {
    if command -v xorriso &>/dev/null; then
        if xorriso -indev "$ISO_FILE" -report_el_torito as_mkisofs 2>&1 | grep -q "efi"; then
            pass "UEFI boot support detected"
        else
            fail "No UEFI boot support detected"
        fi
    else
        skip "xorriso not available for UEFI check"
    fi
}

# Test 7: Check BIOS bootability
test_bios_boot() {
    if command -v xorriso &>/dev/null; then
        if xorriso -indev "$ISO_FILE" -report_el_torito as_mkisofs 2>&1 | grep -qiE "isolinux|syslinux"; then
            pass "BIOS boot support detected"
        else
            # Check for hybrid MBR
            if file "$ISO_FILE" | grep -qi "DOS/MBR"; then
                pass "Hybrid MBR boot support detected"
            else
                fail "No BIOS boot support detected"
            fi
        fi
    else
        skip "xorriso not available for BIOS check"
    fi
}

# Run all tests
info ""
info "Running verification tests..."
info ""

test_file_readable
test_file_size
test_iso_format
test_iso_contents
test_checksum
test_uefi_boot
test_bios_boot

# Test 8: Verify ISO metadata
test_iso_metadata() {
    if command -v xorriso &>/dev/null && [ "$(id -u)" -eq 0 ]; then
        local mount_point
        mount_point=$(mktemp -d)
        
        if mount -o loop,ro "$ISO_FILE" "$mount_point" 2>/dev/null; then
            # Check for Cortex branding
            local has_cortex=false
            if grep -qi "cortex" "$mount_point/.disk/info" 2>/dev/null || \
               grep -qi "cortex" "$mount_point/isolinux/isolinux.cfg" 2>/dev/null || \
               [ -f "$mount_point/preseed/cortex.preseed" ]; then
                has_cortex=true
            fi
            
            umount "$mount_point"
            rmdir "$mount_point"
            
            if [ "$has_cortex" = true ]; then
                pass "ISO metadata contains Cortex branding"
            else
                warn "ISO metadata missing Cortex branding"
            fi
        else
            skip "Could not mount ISO for metadata check"
        fi
    else
        skip "ISO metadata check requires root and xorriso"
    fi
}

# Test 9: Verify preseed file exists
test_preseed_file() {
    if command -v xorriso &>/dev/null && [ "$(id -u)" -eq 0 ]; then
        local mount_point
        mount_point=$(mktemp -d)
        
        if mount -o loop,ro "$ISO_FILE" "$mount_point" 2>/dev/null; then
            if [ -f "$mount_point/preseed/cortex.preseed" ]; then
                pass "Preseed file found in ISO"
                
                # Check preseed syntax (basic)
                if grep -q "^d-i " "$mount_point/preseed/cortex.preseed"; then
                    pass "Preseed file contains valid directives"
                else
                    warn "Preseed file may have syntax issues"
                fi
            else
                fail "Preseed file not found in ISO"
            fi
            
            umount "$mount_point"
            rmdir "$mount_point"
        else
            skip "Could not mount ISO for preseed check"
        fi
    else
        skip "Preseed check requires root and xorriso"
    fi
}

# Run all tests
info ""
info "Running verification tests..."
info ""

test_file_readable
test_file_size
test_iso_format
test_iso_contents
test_checksum
test_uefi_boot
test_bios_boot
test_iso_metadata
test_preseed_file

# Summary
info ""
info "================================================"
info "Verification Summary"
info "================================================"
info "Passed: $PASS"
info "Failed: $FAIL"
info "Skipped: $SKIP"

if [ $FAIL -gt 0 ]; then
    exit 1
else
    exit 0
fi
