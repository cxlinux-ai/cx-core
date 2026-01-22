"""Do Runner Module for Cortex.

This file provides backward compatibility by re-exporting all classes
from the modular do_runner package.

For new code, prefer importing directly from the package:
    from cortex.do_runner import DoHandler, CommandStatus, etc.
"""

# Re-export everything from the modular package
from cortex.do_runner import (
    # Models
    CommandLog,
    CommandStatus,
    DoRun,
    RunMode,
    TaskNode,
    TaskTree,
    TaskType,
    # Database
    DoRunDatabase,
    # Managers
    CortexUserManager,
    ProtectedPathsManager,
    # Terminal
    TerminalMonitor,
    # Executor
    TaskTreeExecutor,
    # Diagnosis
    AutoFixer,
    ErrorDiagnoser,
    # Verification
    ConflictDetector,
    FileUsefulnessAnalyzer,
    VerificationRunner,
    # Handler
    DoHandler,
    get_do_handler,
    setup_cortex_user,
)

__all__ = [
    "CommandLog",
    "CommandStatus",
    "DoRun",
    "RunMode",
    "TaskNode",
    "TaskTree",
    "TaskType",
    "DoRunDatabase",
    "CortexUserManager",
    "ProtectedPathsManager",
    "TerminalMonitor",
    "TaskTreeExecutor",
    "AutoFixer",
    "ErrorDiagnoser",
    "ConflictDetector",
    "FileUsefulnessAnalyzer",
    "VerificationRunner",
    "DoHandler",
    "get_do_handler",
    "setup_cortex_user",
]
