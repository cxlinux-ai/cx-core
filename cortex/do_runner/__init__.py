"""
Do Runner Module for Cortex.

Enables the ask command to write, read, and execute commands to solve problems.
Manages privilege escalation, command logging, and user confirmation flows.

This module is organized into the following submodules:
- models: Data classes and enums (CommandStatus, RunMode, TaskType, etc.)
- database: DoRunDatabase for storing run history
- managers: CortexUserManager, ProtectedPathsManager
- terminal: TerminalMonitor for watching terminal activity
- executor: TaskTreeExecutor for advanced command execution
- diagnosis: ErrorDiagnoser, AutoFixer for error handling
- verification: ConflictDetector, VerificationRunner, FileUsefulnessAnalyzer
- handler: Main DoHandler class
"""

from .database import DoRunDatabase
from .diagnosis import (
    ALL_ERROR_PATTERNS,
    LOGIN_REQUIREMENTS,
    UBUNTU_PACKAGE_MAP,
    UBUNTU_SERVICE_MAP,
    AutoFixer,
    ErrorDiagnoser,
    LoginHandler,
    LoginRequirement,
    get_error_category,
    get_severity,
    is_critical_error,
)

# New structured diagnosis engine
from .diagnosis_v2 import (
    ERROR_PATTERNS,
    DiagnosisEngine,
    DiagnosisResult,
    ErrorCategory,
    ErrorStackEntry,
    ExecutionResult,
    FixCommand,
    FixPlan,
    VariableResolution,
    get_diagnosis_engine,
)
from .executor import TaskTreeExecutor
from .handler import (
    DoHandler,
    get_do_handler,
    setup_cortex_user,
)
from .managers import (
    CortexUserManager,
    ProtectedPathsManager,
)
from .models import (
    CommandLog,
    CommandStatus,
    DoRun,
    RunMode,
    TaskNode,
    TaskTree,
    TaskType,
)
from .terminal import TerminalMonitor
from .verification import (
    ConflictDetector,
    FileUsefulnessAnalyzer,
    VerificationRunner,
)

__all__ = [
    # Models
    "CommandLog",
    "CommandStatus",
    "DoRun",
    "RunMode",
    "TaskNode",
    "TaskTree",
    "TaskType",
    # Database
    "DoRunDatabase",
    # Managers
    "CortexUserManager",
    "ProtectedPathsManager",
    # Terminal
    "TerminalMonitor",
    # Executor
    "TaskTreeExecutor",
    # Diagnosis (legacy)
    "AutoFixer",
    "ErrorDiagnoser",
    "LoginHandler",
    "LoginRequirement",
    "LOGIN_REQUIREMENTS",
    "UBUNTU_PACKAGE_MAP",
    "UBUNTU_SERVICE_MAP",
    "ALL_ERROR_PATTERNS",
    "get_error_category",
    "get_severity",
    "is_critical_error",
    # Diagnosis v2 (structured)
    "DiagnosisEngine",
    "ErrorCategory",
    "DiagnosisResult",
    "FixCommand",
    "FixPlan",
    "VariableResolution",
    "ExecutionResult",
    "ErrorStackEntry",
    "ERROR_PATTERNS",
    "get_diagnosis_engine",
    # Verification
    "ConflictDetector",
    "FileUsefulnessAnalyzer",
    "VerificationRunner",
    # Handler
    "DoHandler",
    "get_do_handler",
    "setup_cortex_user",
]
