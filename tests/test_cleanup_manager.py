"""
Tests for Cleanup Manager Module.

Tests for CleanupManager class and QuarantineItem dataclass.
"""

import pytest
import json
import time
from pathlib import Path
from unittest.mock import patch

from cortex.cleanup.manager import CleanupManager, QuarantineItem


class TestQuarantineItem:
    """Tests for QuarantineItem dataclass."""
    
    def test_create_item(self):
        """Test creating a quarantine item."""
        item = QuarantineItem(
            id="abc123",
            original_path="/tmp/test.txt",
            quarantine_path="/home/user/.cortex/trash/abc123_test.txt",
            timestamp=1234567890.0,
            size_bytes=1024
        )
        
        assert item.id == "abc123"
        assert item.original_path == "/tmp/test.txt"
        assert item.size_bytes == 1024


class TestCleanupManager:
    """Tests for CleanupManager class."""
    
    @pytest.fixture
    def manager(self, tmp_path):
        """Create a manager instance with temp quarantine directory."""
        with patch.object(CleanupManager, '__init__', lambda self: None):
            mgr = CleanupManager.__new__(CleanupManager)
            mgr.quarantine_dir = tmp_path / "trash"
            mgr.metadata_file = mgr.quarantine_dir / "metadata.json"
            mgr._ensure_dir()
            return mgr
    
    def test_ensure_dir(self, manager):
        """Test directory creation."""
        assert manager.quarantine_dir.exists()
    
    def test_load_metadata_empty(self, manager):
        """Test loading metadata when file doesn't exist."""
        metadata = manager._load_metadata()
        
        assert metadata == {}
    
    def test_save_and_load_metadata(self, manager):
        """Test saving and loading metadata."""
        test_data = {
            "item1": {"id": "item1", "path": "/test"},
            "item2": {"id": "item2", "path": "/test2"}
        }
        
        manager._save_metadata(test_data)
        loaded = manager._load_metadata()
        
        assert loaded == test_data
    
    def test_load_metadata_invalid_json(self, manager):
        """Test loading invalid JSON metadata."""
        manager.metadata_file.write_text("not valid json")
        
        metadata = manager._load_metadata()
        
        assert metadata == {}
    
    def test_quarantine_file_success(self, manager, tmp_path):
        """Test quarantining a file successfully."""
        # Create a test file
        test_file = tmp_path / "to_quarantine.txt"
        test_file.write_text("test content")
        
        item_id = manager.quarantine_file(str(test_file))
        
        assert item_id is not None
        assert len(item_id) == 8
        assert not test_file.exists()  # Original moved
        
        # Check metadata
        metadata = manager._load_metadata()
        assert item_id in metadata
    
    def test_quarantine_file_nonexistent(self, manager):
        """Test quarantining a nonexistent file."""
        item_id = manager.quarantine_file("/nonexistent/file.txt")
        
        assert item_id is None
    
    def test_restore_item_success(self, manager, tmp_path):
        """Test restoring a quarantined item successfully."""
        # First quarantine a file
        test_file = tmp_path / "to_restore.txt"
        test_file.write_text("restore me")
        
        item_id = manager.quarantine_file(str(test_file))
        assert not test_file.exists()
        
        # Now restore it
        success = manager.restore_item(item_id)
        
        assert success is True
        assert test_file.exists()
        assert test_file.read_text() == "restore me"
    
    def test_restore_item_not_found(self, manager):
        """Test restoring a nonexistent item."""
        success = manager.restore_item("nonexistent_id")
        
        assert success is False
    
    def test_restore_item_missing_quarantine_file(self, manager, tmp_path):
        """Test restoring when quarantine file is missing."""
        # Create metadata without actual file
        metadata = {
            "fake_id": {
                "id": "fake_id",
                "original_path": str(tmp_path / "original.txt"),
                "quarantine_path": str(manager.quarantine_dir / "missing.txt"),
                "timestamp": time.time(),
                "size_bytes": 100
            }
        }
        manager._save_metadata(metadata)
        
        success = manager.restore_item("fake_id")
        
        assert success is False
    
    def test_list_items_empty(self, manager):
        """Test listing items when empty."""
        items = manager.list_items()
        
        assert items == []
    
    def test_list_items_sorted(self, manager, tmp_path):
        """Test listing items sorted by timestamp."""
        # Create and quarantine multiple files
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("1")
        file2.write_text("2")
        
        id1 = manager.quarantine_file(str(file1))
        time.sleep(0.1)
        id2 = manager.quarantine_file(str(file2))
        
        items = manager.list_items()
        
        assert len(items) == 2
        # Most recent should be first
        assert items[0].id == id2
        assert items[1].id == id1
    
    def test_cleanup_old_items_none_expired(self, manager, tmp_path):
        """Test cleanup when no items are expired."""
        # Quarantine a file
        test_file = tmp_path / "fresh.txt"
        test_file.write_text("fresh")
        _ = manager.quarantine_file(str(test_file))
        
        manager.cleanup_old_items(days=30)
        
        # Item should still exist
        items = manager.list_items()
        assert len(items) == 1
    
    def test_cleanup_old_items_expired(self, manager, tmp_path):
        """Test cleanup of expired items."""
        # Create metadata with old timestamp
        old_time = time.time() - (40 * 86400)  # 40 days ago
        quarantine_file = manager.quarantine_dir / "old_file.txt"
        quarantine_file.write_text("old")
        
        metadata = {
            "old_id": {
                "id": "old_id",
                "original_path": str(tmp_path / "original.txt"),
                "quarantine_path": str(quarantine_file),
                "timestamp": old_time,
                "size_bytes": 100
            }
        }
        manager._save_metadata(metadata)
        
        manager.cleanup_old_items(days=30)
        
        # Item should be removed
        items = manager.list_items()
        assert len(items) == 0
        assert not quarantine_file.exists()
    
    def test_quarantine_preserves_filename(self, manager, tmp_path):
        """Test that quarantine preserves original filename."""
        test_file = tmp_path / "important_file.txt"
        test_file.write_text("important")
        
        item_id = manager.quarantine_file(str(test_file))
        
        metadata = manager._load_metadata()
        quarantine_path = Path(metadata[item_id]["quarantine_path"])
        
        assert "important_file.txt" in quarantine_path.name


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
