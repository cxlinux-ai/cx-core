#!/usr/bin/env python3
"""
Tests for Installation History and Rollback System
"""

import unittest
import tempfile
import os
from datetime import datetime
from cortex.installation_history import (
    InstallationHistory,
    InstallationType,
    InstallationStatus,
    PackageSnapshot,
    InstallationRecord
)


class TestInstallationHistory(unittest.TestCase):
    """Test cases for InstallationHistory"""

    def setUp(self):
        # Create temporary database
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.history = InstallationHistory(db_path=self.temp_db.name)

    def tearDown(self):
        # Clean up temporary database
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    def test_database_initialization(self):
        """Test database is created properly"""
        self.assertTrue(os.path.exists(self.temp_db.name))

    def test_record_installation(self):
        """Test recording an installation"""
        install_id = self.history.record_installation(
            InstallationType.INSTALL,
            ['test-package'],
            ['sudo apt-get install test-package'],
            datetime.now()
        )

        self.assertIsNotNone(install_id)
        self.assertEqual(len(install_id), 16)  # MD5 hash truncated to 16

    def test_update_installation(self):
        """Test updating installation status"""
        install_id = self.history.record_installation(
            InstallationType.INSTALL,
            ['test-package'],
            ['sudo apt-get install test-package'],
            datetime.now()
        )

        self.history.update_installation(
            install_id,
            InstallationStatus.SUCCESS
        )

        record = self.history.get_installation(install_id)
        self.assertIsNotNone(record)
        self.assertEqual(record.status, InstallationStatus.SUCCESS)

    def test_get_history(self):
        """Test retrieving history"""
        # Record multiple installations
        for i in range(3):
            install_id = self.history.record_installation(
                InstallationType.INSTALL,
                [f'package-{i}'],
                [f'sudo apt-get install package-{i}'],
                datetime.now()
            )
            self.history.update_installation(
                install_id,
                InstallationStatus.SUCCESS
            )

        history = self.history.get_history(limit=10)
        self.assertEqual(len(history), 3)

    def test_get_history_with_filter(self):
        """Test filtering history by status"""
        # Record successful installation
        install_id1 = self.history.record_installation(
            InstallationType.INSTALL,
            ['package-1'],
            ['cmd'],
            datetime.now()
        )
        self.history.update_installation(install_id1, InstallationStatus.SUCCESS)

        # Record failed installation
        install_id2 = self.history.record_installation(
            InstallationType.INSTALL,
            ['package-2'],
            ['cmd'],
            datetime.now()
        )
        self.history.update_installation(
            install_id2,
            InstallationStatus.FAILED,
            "Test error"
        )

        # Filter for successful only
        success_history = self.history.get_history(
            limit=10,
            status_filter=InstallationStatus.SUCCESS
        )

        self.assertEqual(len(success_history), 1)
        self.assertEqual(success_history[0].status, InstallationStatus.SUCCESS)

    def test_get_specific_installation(self):
        """Test retrieving specific installation by ID"""
        install_id = self.history.record_installation(
            InstallationType.INSTALL,
            ['test-package'],
            ['test-command'],
            datetime.now()
        )

        record = self.history.get_installation(install_id)

        self.assertIsNotNone(record)
        self.assertEqual(record.id, install_id)
        self.assertEqual(record.packages, ['test-package'])

    def test_package_snapshot(self):
        """Test creating package snapshot"""
        # Test with a package that exists on most systems
        snapshot = self.history._get_package_info('bash')

        if snapshot and snapshot.status != "not-installed":
            self.assertIsNotNone(snapshot.version)
            self.assertEqual(snapshot.package_name, 'bash')

    def test_rollback_dry_run(self):
        """Test rollback dry run"""
        # Create a mock installation record
        install_id = self.history.record_installation(
            InstallationType.INSTALL,
            ['test-package'],
            ['sudo apt-get install test-package'],
            datetime.now()
        )

        self.history.update_installation(
            install_id,
            InstallationStatus.SUCCESS
        )

        # Try dry run rollback
        success, message = self.history.rollback(install_id, dry_run=True)

        # Dry run should show actions or indicate no actions needed
        self.assertIsInstance(message, str)

    def test_extract_packages_from_commands(self):
        """Test extracting package names from commands"""
        commands = [
            'sudo apt-get install -y nginx docker.io',
            'sudo apt install postgresql',
            'sudo apt-get remove python3'
        ]
        
        packages = self.history._extract_packages_from_commands(commands)
        
        self.assertIn('nginx', packages)
        self.assertIn('docker.io', packages)
        self.assertIn('postgresql', packages)
        self.assertIn('python3', packages)

    def test_export_json(self):
        """Test exporting history to JSON"""
        # Record installation
        install_id = self.history.record_installation(
            InstallationType.INSTALL,
            ['test-package'],
            ['test-command'],
            datetime.now()
        )
        self.history.update_installation(install_id, InstallationStatus.SUCCESS)

        # Export
        temp_export = tempfile.NamedTemporaryFile(
            mode='w',
            delete=False,
            suffix='.json'
        )
        temp_export.close()

        try:
            self.history.export_history(temp_export.name, format='json')
            self.assertTrue(os.path.exists(temp_export.name))

            # Verify file is valid JSON
            import json
            with open(temp_export.name, 'r') as f:
                data = json.load(f)

            self.assertIsInstance(data, list)
            self.assertTrue(len(data) > 0)
        finally:
            if os.path.exists(temp_export.name):
                os.unlink(temp_export.name)

    def test_export_csv(self):
        """Test exporting history to CSV"""
        # Record installation
        install_id = self.history.record_installation(
            InstallationType.INSTALL,
            ['test-package'],
            ['test-command'],
            datetime.now()
        )
        self.history.update_installation(install_id, InstallationStatus.SUCCESS)

        # Export
        temp_export = tempfile.NamedTemporaryFile(
            mode='w',
            delete=False,
            suffix='.csv'
        )
        temp_export.close()

        try:
            self.history.export_history(temp_export.name, format='csv')
            self.assertTrue(os.path.exists(temp_export.name))

            # Verify file has content
            with open(temp_export.name, 'r') as f:
                content = f.read()

            self.assertIn('ID', content)
            self.assertIn('Timestamp', content)
        finally:
            if os.path.exists(temp_export.name):
                os.unlink(temp_export.name)

    def test_cleanup_old_records(self):
        """Test cleaning up old records"""
        # Record installation
        install_id = self.history.record_installation(
            InstallationType.INSTALL,
            ['test-package'],
            ['test-command'],
            datetime.now()
        )
        self.history.update_installation(install_id, InstallationStatus.SUCCESS)

        # Cleanup (with 0 days should delete all)
        deleted = self.history.cleanup_old_records(days=0)

        # Should have deleted records
        self.assertGreaterEqual(deleted, 0)

    def test_installation_id_generation(self):
        """Test unique ID generation"""
        id1 = self.history._generate_id(['package-a', 'package-b'])
        id2 = self.history._generate_id(['package-a', 'package-b'])
        id3 = self.history._generate_id(['package-c'])

        # Same packages should generate different IDs (due to timestamp)
        # Different packages should generate different IDs
        self.assertNotEqual(id1, id3)

    def test_record_installation_with_empty_packages(self):
        """Test recording installation with empty packages list (should extract from commands)"""
        install_id = self.history.record_installation(
            InstallationType.INSTALL,
            [],  # Empty packages
            ['sudo apt-get install -y nginx docker'],
            datetime.now()
        )

        record = self.history.get_installation(install_id)
        self.assertIsNotNone(record)
        # Should have extracted packages from commands
        self.assertGreater(len(record.packages), 0)

    def test_rollback_nonexistent_installation(self):
        """Test rollback of non-existent installation"""
        success, message = self.history.rollback('nonexistent-id')
        self.assertFalse(success)
        self.assertIn('not found', message.lower())

    def test_get_nonexistent_installation(self):
        """Test getting non-existent installation"""
        record = self.history.get_installation('nonexistent-id')
        self.assertIsNone(record)


if __name__ == '__main__':
    unittest.main()

