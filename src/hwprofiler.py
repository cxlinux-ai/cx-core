#!/usr/bin/env python3
"""
Hardware Profiling System for Cortex Linux
Detects CPU, GPU, RAM, storage, and network capabilities.
"""

import json
import subprocess
import re
import os
from typing import Dict, List, Optional, Any
from pathlib import Path


class HardwareProfiler:
    """Detects and profiles system hardware."""
    
    def __init__(self):
        self.cpu_info = None
        self.gpu_info = []
        self.ram_info = None
        self.storage_info = []
        self.network_info = None
    
    def detect_cpu(self) -> Dict[str, Any]:
        """
        Detect CPU information: model, cores, architecture.
        
        Returns:
            dict: CPU information with model, cores, and architecture
        """
        cpu_info = {}
        
        try:
            # Read /proc/cpuinfo for CPU details
            with open('/proc/cpuinfo', 'r') as f:
                cpuinfo = f.read()
            
            # Extract model name
            model_match = re.search(r'model name\s*:\s*(.+)', cpuinfo)
            if model_match:
                cpu_info['model'] = model_match.group(1).strip()
            else:
                # Fallback for ARM or other architectures
                model_match = re.search(r'Processor\s*:\s*(.+)', cpuinfo)
                if model_match:
                    cpu_info['model'] = model_match.group(1).strip()
                else:
                    cpu_info['model'] = "Unknown CPU"
            
            # Count physical cores
            physical_cores = 0
            core_ids = set()
            for line in cpuinfo.split('\n'):
                if line.startswith('core id'):
                    core_id = line.split(':')[1].strip()
                    if core_id:
                        core_ids.add(core_id)
                elif line.startswith('physical id'):
                    physical_cores = len(core_ids) if core_ids else 0
            
            # If we couldn't get physical cores, count logical cores
            if physical_cores == 0:
                logical_cores = len([l for l in cpuinfo.split('\n') if l.startswith('processor')])
                cpu_info['cores'] = logical_cores
            else:
                # Get number of physical CPUs
                physical_ids = set()
                for line in cpuinfo.split('\n'):
                    if line.startswith('physical id'):
                        pid = line.split(':')[1].strip()
                        if pid:
                            physical_ids.add(pid)
                cpu_info['cores'] = len(physical_ids) * len(core_ids) if core_ids else len(core_ids)
            
            # Fallback: use nproc if available
            if cpu_info.get('cores', 0) == 0:
                try:
                    result = subprocess.run(['nproc'], capture_output=True, text=True, timeout=1)
                    if result.returncode == 0:
                        cpu_info['cores'] = int(result.stdout.strip())
                except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
                    pass
            
            # Detect architecture
            try:
                result = subprocess.run(['uname', '-m'], capture_output=True, text=True, timeout=1)
                if result.returncode == 0:
                    arch = result.stdout.strip()
                    cpu_info['architecture'] = arch
                else:
                    cpu_info['architecture'] = 'unknown'
            except (subprocess.TimeoutExpired, FileNotFoundError):
                cpu_info['architecture'] = 'unknown'
            
        except Exception as e:
            cpu_info = {
                'model': 'Unknown',
                'cores': 0,
                'architecture': 'unknown',
                'error': str(e)
            }
        
        self.cpu_info = cpu_info
        return cpu_info
    
    def detect_gpu(self) -> List[Dict[str, Any]]:
        """
        Detect GPU information: vendor, model, VRAM, CUDA version.
        
        Returns:
            list: List of GPU information dictionaries
        """
        gpus = []
        
        # Detect NVIDIA GPUs
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        parts = [p.strip() for p in line.split(',')]
                        if len(parts) >= 2:
                            gpu_name = parts[0]
                            vram_mb = int(parts[1]) if parts[1].isdigit() else 0
                            
                            gpu_info = {
                                'vendor': 'NVIDIA',
                                'model': gpu_name,
                                'vram': vram_mb
                            }
                            
                            # Try to get CUDA version
                            try:
                                cuda_result = subprocess.run(
                                    ['nvidia-smi', '--query-gpu=cuda_version', '--format=csv,noheader'],
                                    capture_output=True,
                                    text=True,
                                    timeout=1
                                )
                                if cuda_result.returncode == 0 and cuda_result.stdout.strip():
                                    gpu_info['cuda'] = cuda_result.stdout.strip()
                            except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
                                # Try nvcc as fallback
                                try:
                                    nvcc_result = subprocess.run(
                                        ['nvcc', '--version'],
                                        capture_output=True,
                                        text=True,
                                        timeout=1
                                    )
                                    if nvcc_result.returncode == 0:
                                        version_match = re.search(r'release (\d+\.\d+)', nvcc_result.stdout)
                                        if version_match:
                                            gpu_info['cuda'] = version_match.group(1)
                                except (subprocess.TimeoutExpired, FileNotFoundError):
                                    pass
                            
                            gpus.append(gpu_info)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        # Detect AMD GPUs using lspci
        try:
            result = subprocess.run(
                ['lspci'],
                capture_output=True,
                text=True,
                timeout=1
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'VGA' in line or 'Display' in line:
                        if 'AMD' in line or 'ATI' in line or 'Radeon' in line:
                            # Extract model name
                            model_match = re.search(r'(?:AMD|ATI|Radeon)[\s/]+([A-Za-z0-9\s]+)', line)
                            model = model_match.group(1).strip() if model_match else 'Unknown AMD GPU'
                            
                            # Check if we already have this GPU (avoid duplicates)
                            if not any(g.get('vendor') == 'AMD' and g.get('model') == model for g in gpus):
                                gpu_info = {
                                    'vendor': 'AMD',
                                    'model': model,
                                    'vram': None  # AMD VRAM detection requires rocm-smi or other tools
                                }
                                
                                # Try to get VRAM using rocm-smi if available
                                try:
                                    rocm_result = subprocess.run(
                                        ['rocm-smi', '--showmeminfo', 'vram'],
                                        capture_output=True,
                                        text=True,
                                        timeout=1
                                    )
                                    if rocm_result.returncode == 0:
                                        # Parse VRAM from rocm-smi output
                                        vram_match = re.search(r'(\d+)\s*MB', rocm_result.stdout)
                                        if vram_match:
                                            gpu_info['vram'] = int(vram_match.group(1))
                                except (subprocess.TimeoutExpired, FileNotFoundError):
                                    pass
                                
                                gpus.append(gpu_info)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        # Detect Intel GPUs
        try:
            result = subprocess.run(
                ['lspci'],
                capture_output=True,
                text=True,
                timeout=1
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'VGA' in line or 'Display' in line:
                        if 'Intel' in line:
                            model_match = re.search(r'Intel[^:]*:\s*([^\(]+)', line)
                            model = model_match.group(1).strip() if model_match else 'Unknown Intel GPU'
                            
                            if not any(g.get('vendor') == 'Intel' and g.get('model') == model for g in gpus):
                                gpus.append({
                                    'vendor': 'Intel',
                                    'model': model,
                                    'vram': None  # Intel integrated GPUs share system RAM
                                })
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        self.gpu_info = gpus
        return gpus
    
    def detect_ram(self) -> int:
        """
        Detect total RAM in MB.
        
        Returns:
            int: Total RAM in MB
        """
        try:
            # Read /proc/meminfo
            with open('/proc/meminfo', 'r') as f:
                meminfo = f.read()
            
            # Extract MemTotal
            match = re.search(r'MemTotal:\s+(\d+)\s+kB', meminfo)
            if match:
                ram_kb = int(match.group(1))
                ram_mb = ram_kb // 1024
                self.ram_info = ram_mb
                return ram_mb
            else:
                self.ram_info = 0
                return 0
        except Exception as e:
            self.ram_info = 0
            return 0
    
    def detect_storage(self) -> List[Dict[str, Any]]:
        """
        Detect storage devices: type and size.
        
        Returns:
            list: List of storage device information
        """
        storage_devices = []
        
        try:
            # Use lsblk to get block device information
            result = subprocess.run(
                ['lsblk', '-d', '-o', 'NAME,TYPE,SIZE', '-n'],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 2:
                            device_name = parts[0]
                            
                            # Skip loop devices and other virtual devices
                            if device_name.startswith('loop') or device_name.startswith('ram'):
                                continue
                            
                            device_type = parts[1] if len(parts) > 1 else 'unknown'
                            size_str = parts[2] if len(parts) > 2 else '0'
                            
                            # Convert size to MB
                            size_mb = 0
                            if 'G' in size_str.upper():
                                size_mb = int(float(re.sub(r'[^0-9.]', '', size_str.replace('G', '').replace('g', ''))) * 1024)
                            elif 'T' in size_str.upper():
                                size_mb = int(float(re.sub(r'[^0-9.]', '', size_str.replace('T', '').replace('t', ''))) * 1024 * 1024)
                            elif 'M' in size_str.upper():
                                size_mb = int(float(re.sub(r'[^0-9.]', '', size_str.replace('M', '').replace('m', ''))))
                            
                            # Determine storage type
                            storage_type = 'unknown'
                            device_path = f'/sys/block/{device_name}'
                            
                            # Check if it's NVMe
                            if 'nvme' in device_name.lower():
                                storage_type = 'nvme'
                            # Check if it's SSD (by checking if it's rotational)
                            elif os.path.exists(f'{device_path}/queue/rotational'):
                                try:
                                    with open(f'{device_path}/queue/rotational', 'r') as f:
                                        is_rotational = f.read().strip() == '1'
                                    storage_type = 'hdd' if is_rotational else 'ssd'
                                except Exception:
                                    storage_type = 'unknown'
                            else:
                                # Fallback: guess based on device name
                                if 'sd' in device_name.lower():
                                    storage_type = 'hdd'  # Default assumption
                                elif 'nvme' in device_name.lower():
                                    storage_type = 'nvme'
                            
                            storage_devices.append({
                                'type': storage_type,
                                'size': size_mb,
                                'device': device_name
                            })
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            pass
        
        self.storage_info = storage_devices
        return storage_devices
    
    def detect_network(self) -> Dict[str, Any]:
        """
        Detect network capabilities.
        
        Returns:
            dict: Network information including interfaces and speeds
        """
        network_info = {
            'interfaces': [],
            'max_speed_mbps': 0
        }
        
        try:
            # Get network interfaces using ip command
            result = subprocess.run(
                ['ip', '-o', 'link', 'show'],
                capture_output=True,
                text=True,
                timeout=1
            )
            
            if result.returncode == 0:
                interfaces = []
                for line in result.stdout.split('\n'):
                    if ': ' in line:
                        parts = line.split(': ')
                        if len(parts) >= 2:
                            interface_name = parts[1].split('@')[0].split()[0] if '@' in parts[1] else parts[1].split()[0]
                            
                            # Skip loopback
                            if interface_name == 'lo':
                                continue
                            
                            # Try to get interface speed
                            speed = None
                            try:
                                speed_path = f'/sys/class/net/{interface_name}/speed'
                                if os.path.exists(speed_path):
                                    with open(speed_path, 'r') as f:
                                        speed_str = f.read().strip()
                                        if speed_str.isdigit():
                                            speed = int(speed_str)
                            except Exception:
                                pass
                            
                            interfaces.append({
                                'name': interface_name,
                                'speed_mbps': speed
                            })
                            
                            if speed and speed > network_info['max_speed_mbps']:
                                network_info['max_speed_mbps'] = speed
                
                network_info['interfaces'] = interfaces
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            pass
        
        self.network_info = network_info
        return network_info
    
    def profile(self) -> Dict[str, Any]:
        """
        Run complete hardware profiling.
        
        Returns:
            dict: Complete hardware profile in JSON format
        """
        # Run all detection methods
        cpu = self.detect_cpu()
        gpu = self.detect_gpu()
        ram = self.detect_ram()
        storage = self.detect_storage()
        network = self.detect_network()
        
        # Build result dictionary
        result = {
            'cpu': {
                'model': cpu.get('model', 'Unknown'),
                'cores': cpu.get('cores', 0),
                'architecture': cpu.get('architecture', 'unknown')
            },
            'gpu': gpu,
            'ram': ram,
            'storage': storage,
            'network': network
        }
        
        return result
    
    def to_json(self, indent: int = 2) -> str:
        """
        Convert hardware profile to JSON string.
        
        Args:
            indent: JSON indentation level
            
        Returns:
            str: JSON string representation
        """
        profile = self.profile()
        return json.dumps(profile, indent=indent)


def main():
    """CLI entry point for hardware profiler."""
    import sys
    
    profiler = HardwareProfiler()
    
    try:
        profile = profiler.profile()
        print(profiler.to_json())
        sys.exit(0)
    except Exception as e:
        print(json.dumps({'error': str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

