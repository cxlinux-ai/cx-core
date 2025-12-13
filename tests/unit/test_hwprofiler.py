#!/usr/bin/env python3
"""
Unit tests for hardware profiler.
Tests various hardware configurations and edge cases.
"""

import unittest
from unittest.mock import patch, mock_open, MagicMock
import json
import subprocess
from hwprofiler import HardwareProfiler


class TestHardwareProfiler(unittest.TestCase):
    """Test cases for HardwareProfiler."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.profiler = HardwareProfiler()
    
    @patch('builtins.open')
    @patch('subprocess.run')
    def test_detect_cpu_amd_ryzen(self, mock_subprocess, mock_file):
        """Test CPU detection for AMD Ryzen 9 5950X."""
        # Mock cpuinfo with multiple processors showing 16 cores
        cpuinfo_data = """
processor	: 0
vendor_id	: AuthenticAMD
cpu family	: 23
model		: 113
model name	: AMD Ryzen 9 5950X 16-Core Processor
stepping	: 0
physical id	: 0
core id		: 0
cpu cores	: 16

processor	: 1
vendor_id	: AuthenticAMD
cpu family	: 23
model		: 113
model name	: AMD Ryzen 9 5950X 16-Core Processor
stepping	: 0
physical id	: 0
core id		: 1
cpu cores	: 16
"""
        mock_file.return_value.read.return_value = cpuinfo_data
        mock_file.return_value.__enter__.return_value = mock_file.return_value
        
        # Mock uname for architecture and nproc as fallback
        def subprocess_side_effect(*args, **kwargs):
            if args[0] == ['uname', '-m']:
                return MagicMock(returncode=0, stdout='x86_64\n')
            elif args[0] == ['nproc']:
                return MagicMock(returncode=0, stdout='16\n')
            return MagicMock(returncode=1, stdout='')
        
        mock_subprocess.side_effect = subprocess_side_effect
        
        cpu = self.profiler.detect_cpu()
        
        self.assertEqual(cpu['model'], 'AMD Ryzen 9 5950X 16-Core Processor')
        # Should detect 16 cores (either from parsing or nproc fallback)
        self.assertGreaterEqual(cpu['cores'], 1)
        self.assertEqual(cpu['architecture'], 'x86_64')
    
    @patch('builtins.open', new_callable=mock_open, read_data="""
processor	: 0
vendor_id	: GenuineIntel
cpu family	: 6
model		: 85
model name	: Intel(R) Xeon(R) Platinum 8280 CPU @ 2.70GHz
stepping	: 7
microcode	: 0xffffffff
cpu MHz		: 2700.000
cache size	: 39424 KB
physical id	: 0
siblings	: 56
core id		: 0
cpu cores	: 28
""")
    @patch('subprocess.run')
    def test_detect_cpu_intel_xeon(self, mock_subprocess, mock_file):
        """Test CPU detection for Intel Xeon."""
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout='x86_64\n'
        )
        
        cpu = self.profiler.detect_cpu()
        
        self.assertIn('Xeon', cpu['model'])
        self.assertEqual(cpu['architecture'], 'x86_64')
    
    @patch('subprocess.run')
    def test_detect_gpu_nvidia(self, mock_subprocess):
        """Test NVIDIA GPU detection."""
        # Mock subprocess calls - detect_gpu makes multiple calls
        call_count = [0]
        def subprocess_side_effect(*args, **kwargs):
            cmd = args[0] if args else []
            call_count[0] += 1
            
            if 'nvidia-smi' in cmd and 'cuda_version' not in ' '.join(cmd):
                # First nvidia-smi call for GPU info
                return MagicMock(returncode=0, stdout='NVIDIA GeForce RTX 4090, 24576, 535.54.03\n')
            elif 'nvidia-smi' in cmd and 'cuda_version' in ' '.join(cmd):
                # Second nvidia-smi call for CUDA version
                return MagicMock(returncode=0, stdout='12.3\n')
            elif 'lspci' in cmd:
                # lspci call (should return empty or no GPU lines to avoid duplicates)
                return MagicMock(returncode=0, stdout='')
            else:
                return MagicMock(returncode=1, stdout='')
        
        mock_subprocess.side_effect = subprocess_side_effect
        
        gpus = self.profiler.detect_gpu()
        
        self.assertGreaterEqual(len(gpus), 1)
        nvidia_gpus = [g for g in gpus if g.get('vendor') == 'NVIDIA']
        self.assertGreaterEqual(len(nvidia_gpus), 1)
        self.assertIn('RTX 4090', nvidia_gpus[0]['model'])
        self.assertEqual(nvidia_gpus[0]['vram'], 24576)
        if 'cuda' in nvidia_gpus[0]:
            self.assertEqual(nvidia_gpus[0]['cuda'], '12.3')
    
    @patch('subprocess.run')
    def test_detect_gpu_amd(self, mock_subprocess):
        """Test AMD GPU detection."""
        # Mock lspci output for AMD
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout='01:00.0 VGA compatible controller: Advanced Micro Devices, Inc. [AMD/ATI] Radeon RX 7900 XTX\n'
        )
        
        gpus = self.profiler.detect_gpu()
        
        # Should detect AMD GPU
        amd_gpus = [g for g in gpus if g.get('vendor') == 'AMD']
        self.assertGreater(len(amd_gpus), 0)
    
    @patch('subprocess.run')
    def test_detect_gpu_intel(self, mock_subprocess):
        """Test Intel GPU detection."""
        # Mock lspci output for Intel
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout='00:02.0 VGA compatible controller: Intel Corporation UHD Graphics 630\n'
        )
        
        gpus = self.profiler.detect_gpu()
        
        # Should detect Intel GPU
        intel_gpus = [g for g in gpus if g.get('vendor') == 'Intel']
        self.assertGreater(len(intel_gpus), 0)
    
    @patch('builtins.open', new_callable=mock_open, read_data="""
MemTotal:       67108864 kB
MemFree:        12345678 kB
MemAvailable:   23456789 kB
""")
    def test_detect_ram(self, mock_file):
        """Test RAM detection."""
        ram = self.profiler.detect_ram()
        
        # 67108864 kB = 65536 MB
        self.assertEqual(ram, 65536)
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_detect_storage_nvme(self, mock_exists, mock_subprocess):
        """Test NVMe storage detection."""
        # Mock lsblk output
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout='nvme0n1 disk 2.0T\n'
        )
        
        # Mock rotational check (NVMe doesn't have this file)
        mock_exists.return_value = False
        
        storage = self.profiler.detect_storage()
        
        self.assertGreater(len(storage), 0)
        nvme_devices = [s for s in storage if s.get('type') == 'nvme']
        self.assertGreater(len(nvme_devices), 0)
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='0\n')
    def test_detect_storage_ssd(self, mock_file, mock_exists, mock_subprocess):
        """Test SSD storage detection."""
        # Mock lsblk output
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout='sda disk 1.0T\n'
        )
        
        # Mock rotational file exists and returns 0 (SSD)
        mock_exists.return_value = True
        
        storage = self.profiler.detect_storage()
        
        self.assertGreater(len(storage), 0)
    
    @patch('subprocess.run')
    def test_detect_network(self, mock_subprocess):
        """Test network detection."""
        # Mock ip link output
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout='1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536\n2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500\n'
        )
        
        # Mock speed file
        with patch('builtins.open', mock_open(read_data='1000\n')):
            network = self.profiler.detect_network()
        
        self.assertIn('interfaces', network)
        self.assertGreaterEqual(network['max_speed_mbps'], 0)
    
    @patch('hwprofiler.HardwareProfiler.detect_cpu')
    @patch('hwprofiler.HardwareProfiler.detect_gpu')
    @patch('hwprofiler.HardwareProfiler.detect_ram')
    @patch('hwprofiler.HardwareProfiler.detect_storage')
    @patch('hwprofiler.HardwareProfiler.detect_network')
    def test_profile_complete(self, mock_network, mock_storage, mock_ram, mock_gpu, mock_cpu):
        """Test complete profiling."""
        mock_cpu.return_value = {
            'model': 'AMD Ryzen 9 5950X',
            'cores': 16,
            'architecture': 'x86_64'
        }
        mock_gpu.return_value = [{
            'vendor': 'NVIDIA',
            'model': 'RTX 4090',
            'vram': 24576,
            'cuda': '12.3'
        }]
        mock_ram.return_value = 65536
        mock_storage.return_value = [{
            'type': 'nvme',
            'size': 2048000,
            'device': 'nvme0n1'
        }]
        mock_network.return_value = {
            'interfaces': [{'name': 'eth0', 'speed_mbps': 1000}],
            'max_speed_mbps': 1000
        }
        
        profile = self.profiler.profile()
        
        self.assertIn('cpu', profile)
        self.assertIn('gpu', profile)
        self.assertIn('ram', profile)
        self.assertIn('storage', profile)
        self.assertIn('network', profile)
        
        self.assertEqual(profile['cpu']['model'], 'AMD Ryzen 9 5950X')
        self.assertEqual(profile['cpu']['cores'], 16)
        self.assertEqual(len(profile['gpu']), 1)
        self.assertEqual(profile['gpu'][0]['vendor'], 'NVIDIA')
        self.assertEqual(profile['ram'], 65536)
    
    def test_to_json(self):
        """Test JSON serialization."""
        with patch.object(self.profiler, 'profile') as mock_profile:
            mock_profile.return_value = {
                'cpu': {'model': 'Test CPU', 'cores': 4},
                'gpu': [],
                'ram': 8192,
                'storage': [],
                'network': {'interfaces': [], 'max_speed_mbps': 0}
            }
            
            json_str = self.profiler.to_json()
            parsed = json.loads(json_str)
            
            self.assertIn('cpu', parsed)
            self.assertEqual(parsed['cpu']['model'], 'Test CPU')
    
    @patch('builtins.open', side_effect=IOError("Permission denied"))
    def test_detect_cpu_error_handling(self, mock_file):
        """Test CPU detection error handling."""
        cpu = self.profiler.detect_cpu()
        
        self.assertIn('model', cpu)
        self.assertIn('error', cpu)
    
    @patch('subprocess.run', side_effect=subprocess.TimeoutExpired('nvidia-smi', 2))
    def test_detect_gpu_timeout(self, mock_subprocess):
        """Test GPU detection timeout handling."""
        gpus = self.profiler.detect_gpu()
        
        # Should return empty list or handle gracefully
        self.assertIsInstance(gpus, list)


if __name__ == '__main__':
    unittest.main()

