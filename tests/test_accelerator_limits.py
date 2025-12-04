#!/usr/bin/env python3
"""
Unit tests for Cortex Accelerator-Aware Resource Limits

Tests cover:
- Profile creation with presets
- Resource limit configuration
- Database operations
- cgroups v2 controller (mocked for non-root)
- OOM score management
- Environment variable generation
"""

import os
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from cortex.kernel_features.accelerator_limits import (
    ResourceLimits,
    LimitsDatabase,
    CgroupsV2Controller,
    OOMScoreManager,
    AcceleratorLimitsManager,
    PRESETS,
    WorkloadPreset,
    CORTEX_CGROUP
)


class TestResourceLimits(unittest.TestCase):
    """Test ResourceLimits dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        limits = ResourceLimits(name="test")
        self.assertEqual(limits.name, "test")
        self.assertEqual(limits.preset, "inference")
        self.assertEqual(limits.cpu_quota, 400.0)
        self.assertEqual(limits.cpu_weight, 100)
        self.assertEqual(limits.gpu_ids, [])
        self.assertEqual(limits.oom_score_adj, 0)

    def test_from_preset_inference(self):
        """Test creating limits from inference preset."""
        limits = ResourceLimits.from_preset("my-job", "inference", gpus=2)
        self.assertEqual(limits.name, "my-job")
        self.assertEqual(limits.preset, "inference")
        self.assertEqual(limits.cpu_quota, 400)
        self.assertEqual(limits.memory_max, 32 * 1024**3)
        self.assertEqual(limits.gpu_ids, [0, 1])
        self.assertEqual(limits.oom_score_adj, -500)

    def test_from_preset_training(self):
        """Test creating limits from training preset."""
        limits = ResourceLimits.from_preset("train-job", "training", gpus=4)
        self.assertEqual(limits.cpu_quota, 1600)
        self.assertEqual(limits.memory_max, 128 * 1024**3)
        self.assertEqual(limits.gpu_ids, [0, 1, 2, 3])
        self.assertEqual(limits.oom_score_adj, -800)

    def test_from_preset_batch(self):
        """Test creating limits from batch preset."""
        limits = ResourceLimits.from_preset("batch-job", "batch")
        self.assertEqual(limits.cpu_quota, 800)
        self.assertEqual(limits.memory_max, 64 * 1024**3)
        self.assertEqual(limits.oom_score_adj, 0)

    def test_from_preset_interactive(self):
        """Test creating limits from interactive preset."""
        limits = ResourceLimits.from_preset("dev-env", "interactive")
        self.assertEqual(limits.cpu_quota, 200)
        self.assertEqual(limits.memory_max, 16 * 1024**3)
        self.assertEqual(limits.oom_score_adj, -200)

    def test_from_preset_unknown_falls_back(self):
        """Test unknown preset falls back to inference."""
        limits = ResourceLimits.from_preset("job", "unknown-preset")
        self.assertEqual(limits.preset, "unknown-preset")
        self.assertEqual(limits.cpu_quota, PRESETS["inference"]["cpu_quota"])

    def test_cgroup_path_auto_generated(self):
        """Test cgroup path is auto-generated."""
        limits = ResourceLimits(name="test-job")
        self.assertEqual(limits.cgroup_path, f"{CORTEX_CGROUP}/test-job")

    def test_to_dict_and_from_dict(self):
        """Test serialization roundtrip."""
        original = ResourceLimits.from_preset("roundtrip", "training", gpus=2)
        data = original.to_dict()
        restored = ResourceLimits.from_dict(data)

        self.assertEqual(restored.name, original.name)
        self.assertEqual(restored.preset, original.preset)
        self.assertEqual(restored.cpu_quota, original.cpu_quota)
        self.assertEqual(restored.memory_max, original.memory_max)
        self.assertEqual(restored.gpu_ids, original.gpu_ids)


class TestLimitsDatabase(unittest.TestCase):
    """Test LimitsDatabase storage."""

    def setUp(self):
        """Create temporary database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        self.db = LimitsDatabase(self.db_path)

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_get(self):
        """Test saving and retrieving a profile."""
        limits = ResourceLimits.from_preset("test-save", "inference", gpus=1)
        self.db.save(limits)

        retrieved = self.db.get("test-save")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "test-save")
        self.assertEqual(retrieved.preset, "inference")
        self.assertEqual(retrieved.gpu_ids, [0])

    def test_get_nonexistent(self):
        """Test getting a profile that doesn't exist."""
        result = self.db.get("nonexistent")
        self.assertIsNone(result)

    def test_list_all(self):
        """Test listing all profiles."""
        self.db.save(ResourceLimits.from_preset("job1", "inference"))
        self.db.save(ResourceLimits.from_preset("job2", "training"))
        self.db.save(ResourceLimits.from_preset("job3", "batch"))

        profiles = self.db.list_all()
        self.assertEqual(len(profiles), 3)
        names = [p.name for p in profiles]
        self.assertIn("job1", names)
        self.assertIn("job2", names)
        self.assertIn("job3", names)

    def test_delete(self):
        """Test deleting a profile."""
        self.db.save(ResourceLimits.from_preset("to-delete", "inference"))
        self.assertIsNotNone(self.db.get("to-delete"))

        self.db.delete("to-delete")
        self.assertIsNone(self.db.get("to-delete"))

    def test_update_existing(self):
        """Test updating an existing profile."""
        limits = ResourceLimits.from_preset("update-test", "inference")
        self.db.save(limits)

        # Update with different values
        limits.cpu_quota = 800
        limits.gpu_ids = [0, 1, 2]
        self.db.save(limits)

        retrieved = self.db.get("update-test")
        self.assertEqual(retrieved.cpu_quota, 800)
        self.assertEqual(retrieved.gpu_ids, [0, 1, 2])

    def test_record_and_get_pids(self):
        """Test recording and retrieving PIDs."""
        self.db.save(ResourceLimits.from_preset("pid-test", "inference"))

        self.db.record_pid(1234, "pid-test")
        self.db.record_pid(5678, "pid-test")

        pids = self.db.get_pids("pid-test")
        self.assertEqual(len(pids), 2)
        self.assertIn(1234, pids)
        self.assertIn(5678, pids)


class TestCgroupsV2Controller(unittest.TestCase):
    """Test cgroups v2 controller (with mocks for non-root)."""

    def test_is_available_with_mock(self):
        """Test checking cgroups v2 availability."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "cgroup.controllers").write_text("cpu memory io")

            controller = CgroupsV2Controller(root)
            self.assertTrue(controller.is_available())

    def test_is_available_without_file(self):
        """Test availability check when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            controller = CgroupsV2Controller(Path(tmpdir))
            self.assertFalse(controller.is_available())

    def test_get_available_controllers(self):
        """Test getting list of available controllers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "cgroup.controllers").write_text("cpu memory io pids")

            controller = CgroupsV2Controller(root)
            controllers = controller.get_available_controllers()
            self.assertEqual(controllers, ["cpu", "memory", "io", "pids"])

    def test_create_cgroup_mock(self):
        """Test creating a cgroup directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "cgroup.controllers").write_text("cpu memory")

            controller = CgroupsV2Controller(root)
            success, path = controller.create_cgroup("cortex.slice/test-job")

            self.assertTrue(success)
            self.assertTrue((root / "cortex.slice" / "test-job").exists())

    def test_get_pids_empty(self):
        """Test getting PIDs from empty cgroup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cgroup = root / "test-cgroup"
            cgroup.mkdir()
            (cgroup / "cgroup.procs").write_text("")

            controller = CgroupsV2Controller(root)
            pids = controller.get_pids("test-cgroup")
            self.assertEqual(pids, [])

    def test_get_pids_with_processes(self):
        """Test getting PIDs from cgroup with processes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cgroup = root / "test-cgroup"
            cgroup.mkdir()
            (cgroup / "cgroup.procs").write_text("1234\n5678\n9012")

            controller = CgroupsV2Controller(root)
            pids = controller.get_pids("test-cgroup")
            self.assertEqual(pids, [1234, 5678, 9012])


class TestOOMScoreManager(unittest.TestCase):
    """Test OOM score management."""

    def test_get_oom_score_current_process(self):
        """Test getting OOM score of current process."""
        pid = os.getpid()
        score = OOMScoreManager.get_oom_score_adj(pid)
        self.assertIsNotNone(score)
        self.assertIsInstance(score, int)
        self.assertGreaterEqual(score, -1000)
        self.assertLessEqual(score, 1000)

    def test_get_oom_score_invalid_pid(self):
        """Test getting OOM score of invalid PID."""
        score = OOMScoreManager.get_oom_score_adj(99999999)
        self.assertIsNone(score)


class TestAcceleratorLimitsManager(unittest.TestCase):
    """Test the main manager class."""

    def setUp(self):
        """Create manager with temporary database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / ".cortex" / "limits.db"

        # Patch the default database path
        self.db_patcher = patch(
            'cortex.kernel_features.accelerator_limits.CORTEX_DB',
            self.db_path
        )
        self.db_patcher.start()

        self.mgr = AcceleratorLimitsManager()

    def tearDown(self):
        """Clean up."""
        self.db_patcher.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_profile(self):
        """Test creating a profile."""
        limits = ResourceLimits.from_preset("create-test", "inference", gpus=2)
        result = self.mgr.create(limits)
        self.assertTrue(result)

        # Verify it was saved
        retrieved = self.mgr.db.get("create-test")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "create-test")

    def test_get_env_with_gpus(self):
        """Test getting environment variables for a profile with GPUs."""
        limits = ResourceLimits.from_preset("env-test", "inference", gpus=2)
        self.mgr.create(limits)

        env = self.mgr.get_env("env-test")
        self.assertIn("CUDA_VISIBLE_DEVICES", env)
        self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "0,1")
        self.assertIn("HIP_VISIBLE_DEVICES", env)
        self.assertIn("OMP_NUM_THREADS", env)

    def test_get_env_no_gpus(self):
        """Test environment variables when no GPUs configured."""
        limits = ResourceLimits.from_preset("no-gpu", "batch", gpus=0)
        self.mgr.create(limits)

        env = self.mgr.get_env("no-gpu")
        self.assertNotIn("CUDA_VISIBLE_DEVICES", env)
        self.assertIn("OMP_NUM_THREADS", env)

    def test_get_env_nonexistent_profile(self):
        """Test getting env for nonexistent profile."""
        env = self.mgr.get_env("nonexistent")
        self.assertEqual(env, {})

    def test_delete_profile(self):
        """Test deleting a profile."""
        limits = ResourceLimits.from_preset("delete-test", "inference")
        self.mgr.create(limits)

        self.assertIsNotNone(self.mgr.db.get("delete-test"))
        self.mgr.delete("delete-test")
        self.assertIsNone(self.mgr.db.get("delete-test"))

    def test_cpu_threads_calculation(self):
        """Test that CPU thread count is calculated correctly."""
        # Training preset has 1600% CPU = 16 cores
        limits = ResourceLimits.from_preset("threads-test", "training")
        self.mgr.create(limits)

        env = self.mgr.get_env("threads-test")
        self.assertEqual(env["OMP_NUM_THREADS"], "16")
        self.assertEqual(env["MKL_NUM_THREADS"], "16")


class TestPresets(unittest.TestCase):
    """Test preset configurations."""

    def test_all_presets_exist(self):
        """Test all expected presets are defined."""
        expected = ["inference", "training", "batch", "interactive"]
        for preset in expected:
            self.assertIn(preset, PRESETS)

    def test_preset_has_required_fields(self):
        """Test each preset has required fields."""
        required = ["cpu_quota", "memory_gb", "oom_score_adj", "gpu_percent"]
        for name, config in PRESETS.items():
            for field in required:
                self.assertIn(field, config, f"Preset {name} missing {field}")

    def test_workload_preset_enum(self):
        """Test WorkloadPreset enum values."""
        self.assertEqual(WorkloadPreset.INFERENCE.value, "inference")
        self.assertEqual(WorkloadPreset.TRAINING.value, "training")
        self.assertEqual(WorkloadPreset.BATCH.value, "batch")
        self.assertEqual(WorkloadPreset.INTERACTIVE.value, "interactive")


class TestCLI(unittest.TestCase):
    """Test CLI argument parsing."""

    def test_help_output(self):
        """Test that help doesn't crash."""
        from cortex.kernel_features.accelerator_limits import main
        import sys
        from io import StringIO

        old_argv = sys.argv
        old_stdout = sys.stdout

        try:
            sys.argv = ['accelerator_limits', '--help']
            sys.stdout = StringIO()
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 0)
        finally:
            sys.argv = old_argv
            sys.stdout = old_stdout


if __name__ == "__main__":
    unittest.main(verbosity=2)
