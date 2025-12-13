"""
Tests for Transaction History and Undo Module

Issue: #258
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from cortex.transaction_history import (
    TransactionHistory,
    UndoManager,
    Transaction,
    TransactionType,
    TransactionStatus,
    PackageState,
    get_history,
    get_undo_manager,
    record_install,
    record_remove,
    show_history,
    undo_last
)


class TestPackageState:
    """Tests for PackageState dataclass."""
    
    def test_default_values(self):
        """Test default values."""
        state = PackageState(name="nginx")
        
        assert state.name == "nginx"
        assert state.version is None
        assert state.installed is False
        assert state.config_files == []
        assert state.dependencies == []
    
    def test_to_dict(self):
        """Test serialization to dict."""
        state = PackageState(
            name="nginx",
            version="1.24.0",
            installed=True,
            config_files=["/etc/nginx/nginx.conf"],
            dependencies=["libc6"]
        )
        
        data = state.to_dict()
        
        assert data["name"] == "nginx"
        assert data["version"] == "1.24.0"
        assert data["installed"] is True
        assert "/etc/nginx/nginx.conf" in data["config_files"]
    
    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "name": "redis",
            "version": "7.0.0",
            "installed": True,
            "config_files": ["/etc/redis/redis.conf"],
            "dependencies": ["libc6", "libssl3"]
        }
        
        state = PackageState.from_dict(data)
        
        assert state.name == "redis"
        assert state.version == "7.0.0"
        assert state.installed is True


class TestTransaction:
    """Tests for Transaction dataclass."""
    
    def test_default_values(self):
        """Test default values."""
        tx = Transaction(
            id="tx_001",
            transaction_type=TransactionType.INSTALL,
            packages=["nginx"],
            timestamp=datetime.now()
        )
        
        assert tx.id == "tx_001"
        assert tx.status == TransactionStatus.PENDING
        assert tx.before_state == {}
        assert tx.after_state == {}
    
    def test_to_dict(self):
        """Test serialization."""
        tx = Transaction(
            id="tx_002",
            transaction_type=TransactionType.INSTALL,
            packages=["nginx", "redis"],
            timestamp=datetime(2024, 1, 15, 10, 30),
            status=TransactionStatus.COMPLETED,
            command="cortex install nginx redis",
            user="testuser",
            duration_seconds=5.5
        )
        
        data = tx.to_dict()
        
        assert data["id"] == "tx_002"
        assert data["transaction_type"] == "install"
        assert data["packages"] == ["nginx", "redis"]
        assert data["status"] == "completed"
    
    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "id": "tx_003",
            "transaction_type": "remove",
            "packages": ["vim"],
            "timestamp": "2024-01-15T10:30:00",
            "status": "completed",
            "before_state": {},
            "after_state": {},
            "command": "cortex remove vim",
            "user": "root",
            "duration_seconds": 2.0,
            "error_message": None,
            "rollback_commands": ["sudo apt install -y vim"],
            "is_rollback_safe": True,
            "rollback_warning": None
        }
        
        tx = Transaction.from_dict(data)
        
        assert tx.id == "tx_003"
        assert tx.transaction_type == TransactionType.REMOVE
        assert tx.packages == ["vim"]


class TestTransactionHistory:
    """Tests for TransactionHistory class."""
    
    @pytest.fixture
    def history(self, tmp_path):
        """Create a history instance with temp database."""
        db_path = tmp_path / "test_history.db"
        return TransactionHistory(db_path)
    
    def test_init_creates_database(self, history):
        """Test that initialization creates the database."""
        assert history.db_path.exists()
    
    def test_generate_id(self, history):
        """Test ID generation."""
        id1 = history._generate_id()
        id2 = history._generate_id()
        
        assert id1.startswith("tx_")
        assert id1 != id2
    
    @patch('subprocess.run')
    def test_begin_transaction(self, mock_run, history):
        """Test beginning a transaction."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        tx = history.begin_transaction(
            TransactionType.INSTALL,
            ["nginx"],
            "cortex install nginx"
        )
        
        assert tx.id.startswith("tx_")
        assert tx.transaction_type == TransactionType.INSTALL
        assert tx.packages == ["nginx"]
        assert tx.status == TransactionStatus.IN_PROGRESS
    
    @patch('subprocess.run')
    def test_complete_transaction_success(self, mock_run, history):
        """Test completing a transaction successfully."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        tx = history.begin_transaction(
            TransactionType.INSTALL,
            ["nginx"],
            ""
        )
        
        history.complete_transaction(tx, success=True)
        
        assert tx.status == TransactionStatus.COMPLETED
        assert tx.duration_seconds > 0
    
    @patch('subprocess.run')
    def test_complete_transaction_failure(self, mock_run, history):
        """Test completing a failed transaction."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        tx = history.begin_transaction(
            TransactionType.INSTALL,
            ["nginx"],
            ""
        )
        
        history.complete_transaction(tx, success=False, error_message="Download failed")
        
        assert tx.status == TransactionStatus.FAILED
        assert tx.error_message == "Download failed"
    
    @patch('subprocess.run')
    def test_get_transaction(self, mock_run, history):
        """Test retrieving a transaction by ID."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        tx = history.begin_transaction(
            TransactionType.INSTALL,
            ["nginx"],
            ""
        )
        
        retrieved = history.get_transaction(tx.id)
        
        assert retrieved is not None
        assert retrieved.id == tx.id
        assert retrieved.packages == ["nginx"]
    
    def test_get_transaction_not_found(self, history):
        """Test retrieving non-existent transaction."""
        result = history.get_transaction("nonexistent_id")
        assert result is None
    
    @patch('subprocess.run')
    def test_get_recent(self, mock_run, history):
        """Test getting recent transactions."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        # Create multiple transactions
        for pkg in ["nginx", "redis", "postgresql"]:
            tx = history.begin_transaction(
                TransactionType.INSTALL,
                [pkg],
                ""
            )
            history.complete_transaction(tx, success=True)
        
        recent = history.get_recent(limit=2)
        
        assert len(recent) == 2
        # Most recent should be first
        assert "postgresql" in recent[0].packages
    
    @patch('subprocess.run')
    def test_get_recent_with_filter(self, mock_run, history):
        """Test getting recent with status filter."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        tx1 = history.begin_transaction(TransactionType.INSTALL, ["nginx"], "")
        history.complete_transaction(tx1, success=True)
        
        tx2 = history.begin_transaction(TransactionType.INSTALL, ["redis"], "")
        history.complete_transaction(tx2, success=False, error_message="Error")
        
        completed = history.get_recent(status_filter=TransactionStatus.COMPLETED)
        failed = history.get_recent(status_filter=TransactionStatus.FAILED)
        
        assert all(t.status == TransactionStatus.COMPLETED for t in completed)
        assert all(t.status == TransactionStatus.FAILED for t in failed)
    
    @patch('subprocess.run')
    def test_search_by_package(self, mock_run, history):
        """Test searching by package name."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        tx1 = history.begin_transaction(TransactionType.INSTALL, ["nginx"], "")
        history.complete_transaction(tx1, success=True)
        
        tx2 = history.begin_transaction(TransactionType.INSTALL, ["redis"], "")
        history.complete_transaction(tx2, success=True)
        
        results = history.search(package="nginx")
        
        assert len(results) >= 1
        assert all("nginx" in t.packages for t in results)
    
    @patch('subprocess.run')
    def test_search_by_type(self, mock_run, history):
        """Test searching by transaction type."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        tx1 = history.begin_transaction(TransactionType.INSTALL, ["nginx"], "")
        history.complete_transaction(tx1, success=True)
        
        tx2 = history.begin_transaction(TransactionType.REMOVE, ["vim"], "")
        history.complete_transaction(tx2, success=True)
        
        installs = history.search(transaction_type=TransactionType.INSTALL)
        removes = history.search(transaction_type=TransactionType.REMOVE)
        
        assert all(t.transaction_type == TransactionType.INSTALL for t in installs)
        assert all(t.transaction_type == TransactionType.REMOVE for t in removes)
    
    @patch('subprocess.run')
    def test_get_stats(self, mock_run, history):
        """Test getting statistics."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        tx = history.begin_transaction(TransactionType.INSTALL, ["nginx"], "")
        history.complete_transaction(tx, success=True)
        
        stats = history.get_stats()
        
        assert "total_transactions" in stats
        assert "by_type" in stats
        assert "by_status" in stats
        assert stats["total_transactions"] >= 1
    
    def test_calculate_rollback_install(self, history):
        """Test rollback commands for install."""
        before_state = {
            "nginx": PackageState(name="nginx", installed=False)
        }
        
        commands = history._calculate_rollback_commands(
            TransactionType.INSTALL,
            before_state
        )
        
        assert any("remove" in cmd for cmd in commands)
        assert any("nginx" in cmd for cmd in commands)
    
    def test_calculate_rollback_remove(self, history):
        """Test rollback commands for remove."""
        before_state = {
            "nginx": PackageState(name="nginx", version="1.24.0", installed=True)
        }
        
        commands = history._calculate_rollback_commands(
            TransactionType.REMOVE,
            before_state
        )
        
        assert any("install" in cmd for cmd in commands)
        assert any("nginx" in cmd for cmd in commands)


class TestUndoManager:
    """Tests for UndoManager class."""
    
    @pytest.fixture
    def manager(self, tmp_path):
        """Create an undo manager with temp database."""
        history = TransactionHistory(tmp_path / "test_history.db")
        return UndoManager(history)
    
    @patch('subprocess.run')
    def test_can_undo_completed(self, mock_run, manager):
        """Test can_undo for completed transaction."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        tx = manager.history.begin_transaction(
            TransactionType.INSTALL,
            ["nginx"],
            ""
        )
        manager.history.complete_transaction(tx, success=True)
        
        can_undo, reason = manager.can_undo(tx.id)
        
        # Can undo if rollback commands exist
        assert isinstance(can_undo, bool)
        assert isinstance(reason, str)
    
    def test_can_undo_not_found(self, manager):
        """Test can_undo for non-existent transaction."""
        can_undo, reason = manager.can_undo("nonexistent")
        
        assert can_undo is False
        assert "not found" in reason.lower()
    
    @patch('subprocess.run')
    def test_can_undo_failed(self, mock_run, manager):
        """Test can_undo for failed transaction."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        tx = manager.history.begin_transaction(
            TransactionType.INSTALL,
            ["nginx"],
            ""
        )
        manager.history.complete_transaction(tx, success=False, error_message="Error")
        
        can_undo, reason = manager.can_undo(tx.id)
        
        assert can_undo is False
    
    @patch('subprocess.run')
    def test_preview_undo(self, mock_run, manager):
        """Test previewing an undo operation."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        tx = manager.history.begin_transaction(
            TransactionType.INSTALL,
            ["nginx"],
            ""
        )
        manager.history.complete_transaction(tx, success=True)
        
        preview = manager.preview_undo(tx.id)
        
        assert "transaction_id" in preview
        assert "commands" in preview
        assert "is_safe" in preview
    
    def test_preview_undo_not_found(self, manager):
        """Test preview for non-existent transaction."""
        preview = manager.preview_undo("nonexistent")
        
        assert "error" in preview
    
    @patch('subprocess.run')
    def test_undo_dry_run(self, mock_run, manager):
        """Test undo in dry run mode."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        tx = manager.history.begin_transaction(
            TransactionType.INSTALL,
            ["nginx"],
            ""
        )
        # Manually add rollback commands
        tx.rollback_commands = ["sudo apt remove -y nginx"]
        manager.history.complete_transaction(tx, success=True)
        
        result = manager.undo(tx.id, dry_run=True)
        
        assert result["dry_run"] is True
        assert result["success"] is True
    
    @patch('subprocess.run')
    def test_undo_not_found(self, mock_run, manager):
        """Test undo for non-existent transaction."""
        result = manager.undo("nonexistent")
        
        assert result["success"] is False
        assert "not found" in result["error"].lower()
    
    @patch('subprocess.run')
    def test_undo_last(self, mock_run, manager):
        """Test undoing the last transaction."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        tx = manager.history.begin_transaction(
            TransactionType.INSTALL,
            ["nginx"],
            ""
        )
        tx.rollback_commands = ["sudo apt remove -y nginx"]
        manager.history.complete_transaction(tx, success=True)
        
        result = manager.undo_last(dry_run=True)
        
        assert "transaction_id" in result or "error" in result
    
    def test_undo_last_no_transactions(self, manager):
        """Test undo_last with no transactions."""
        result = manager.undo_last()
        
        assert result["success"] is False


class TestTransactionTypes:
    """Tests for TransactionType enum."""
    
    def test_all_types_exist(self):
        """Test that all expected types exist."""
        expected = [
            "INSTALL", "REMOVE", "UPGRADE", "DOWNGRADE",
            "AUTOREMOVE", "PURGE", "CONFIGURE", "BATCH"
        ]
        
        actual = [t.name for t in TransactionType]
        
        for e in expected:
            assert e in actual
    
    def test_type_values(self):
        """Test type values are lowercase."""
        for t in TransactionType:
            assert t.value == t.name.lower()


class TestTransactionStatus:
    """Tests for TransactionStatus enum."""
    
    def test_all_statuses_exist(self):
        """Test that all expected statuses exist."""
        expected = [
            "PENDING", "IN_PROGRESS", "COMPLETED",
            "FAILED", "ROLLED_BACK", "PARTIALLY_COMPLETED"
        ]
        
        actual = [s.name for s in TransactionStatus]
        
        for e in expected:
            assert e in actual


class TestGlobalFunctions:
    """Tests for module-level convenience functions."""
    
    def test_get_history_singleton(self):
        """Test that get_history returns singleton."""
        h1 = get_history()
        h2 = get_history()
        
        assert h1 is h2
    
    def test_get_undo_manager_singleton(self):
        """Test that get_undo_manager returns singleton."""
        m1 = get_undo_manager()
        m2 = get_undo_manager()
        
        assert m1 is m2
    
    @patch('subprocess.run')
    def test_record_install(self, mock_run):
        """Test record_install convenience function."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        tx = record_install(["nginx"], "cortex install nginx")
        
        assert tx is not None
        assert tx.transaction_type == TransactionType.INSTALL
    
    @patch('subprocess.run')
    def test_record_remove(self, mock_run):
        """Test record_remove convenience function."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        tx = record_remove(["nginx"], "cortex remove nginx")
        
        assert tx is not None
        assert tx.transaction_type == TransactionType.REMOVE
    
    def test_show_history(self):
        """Test show_history convenience function."""
        result = show_history(limit=5)
        
        assert isinstance(result, list)
    
    def test_undo_last(self):
        """Test undo_last convenience function."""
        result = undo_last(dry_run=True)
        
        assert isinstance(result, dict)


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    @pytest.fixture
    def history(self, tmp_path):
        return TransactionHistory(tmp_path / "test_history.db")
    
    def test_empty_packages_list(self, history):
        """Test transaction with empty packages list."""
        tx = history.begin_transaction(
            TransactionType.INSTALL,
            [],
            ""
        )
        
        assert tx.packages == []
        assert tx.before_state == {}
    
    @patch('subprocess.run')
    def test_many_packages(self, mock_run, history):
        """Test transaction with many packages."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        packages = [f"package_{i}" for i in range(100)]
        tx = history.begin_transaction(
            TransactionType.INSTALL,
            packages,
            ""
        )
        
        assert len(tx.packages) == 100
    
    def test_special_characters_in_package(self, history):
        """Test package names with special characters."""
        tx = history.begin_transaction(
            TransactionType.INSTALL,
            ["lib32-gcc-libs", "python3.11-venv", "node@18"],
            ""
        )
        
        assert len(tx.packages) == 3
    
    @patch('subprocess.run')
    def test_concurrent_transactions(self, mock_run, history):
        """Test handling concurrent transactions."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        tx1 = history.begin_transaction(TransactionType.INSTALL, ["pkg1"], "")
        tx2 = history.begin_transaction(TransactionType.INSTALL, ["pkg2"], "")
        
        # Both should have unique IDs
        assert tx1.id != tx2.id
        
        # Complete in reverse order
        history.complete_transaction(tx2, success=True)
        history.complete_transaction(tx1, success=True)
        
        # Both should be saved
        assert history.get_transaction(tx1.id) is not None
        assert history.get_transaction(tx2.id) is not None


class TestIntegration:
    """Integration tests for the full workflow."""
    
    @pytest.fixture
    def setup(self, tmp_path):
        history = TransactionHistory(tmp_path / "test_history.db")
        manager = UndoManager(history)
        return history, manager
    
    @patch('subprocess.run')
    def test_full_install_undo_workflow(self, mock_run, setup):
        """Test complete install and undo workflow."""
        history, manager = setup
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        
        # Step 1: Install
        tx = history.begin_transaction(
            TransactionType.INSTALL,
            ["nginx"],
            "cortex install nginx"
        )
        tx.rollback_commands = ["sudo apt remove -y nginx"]
        history.complete_transaction(tx, success=True)
        
        # Step 2: Verify in history
        recent = history.get_recent(1)
        assert len(recent) == 1
        assert recent[0].id == tx.id
        
        # Step 3: Preview undo
        preview = manager.preview_undo(tx.id)
        assert "commands" in preview
        
        # Step 4: Execute undo
        result = manager.undo(tx.id)
        
        # Step 5: Verify status changed
        updated_tx = history.get_transaction(tx.id)
        assert updated_tx.status in [
            TransactionStatus.ROLLED_BACK,
            TransactionStatus.PARTIALLY_COMPLETED
        ]
    
    @patch('subprocess.run')
    def test_batch_operations(self, mock_run, setup):
        """Test batch operations."""
        history, manager = setup
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        packages = ["nginx", "redis", "postgresql", "mongodb"]
        
        tx = history.begin_transaction(
            TransactionType.BATCH,
            packages,
            "cortex install web-stack"
        )
        
        history.complete_transaction(tx, success=True)
        
        assert tx.transaction_type == TransactionType.BATCH
        assert len(tx.packages) == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
