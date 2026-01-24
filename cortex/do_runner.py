"""Do Runner Module for Cortex.

This file provides backward compatibility by re-exporting all classes
from the modular do_runner package.

For new code, prefer importing directly from the package:
    from cortex.do_runner import DoHandler, CommandStatus, etc.
"""

# Re-export everything from the modular package
from cortex.do_runner import (  # Diagnosis; Models; Verification; Managers; Handler; Database; Executor; Terminal
    AutoFixer,
    CommandLog,
    CommandStatus,
    ConflictDetector,
    CortexUserManager,
    DoHandler,
    DoRun,
    DoRunDatabase,
    ErrorDiagnoser,
    FileUsefulnessAnalyzer,
    ProtectedPathsManager,
    RunMode,
    TaskNode,
    TaskTree,
    TaskTreeExecutor,
    TaskType,
    TerminalMonitor,
    VerificationRunner,
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
