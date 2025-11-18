"""
Cortex - The AI-Native Operating System
========================================

A comprehensive system for intelligent Linux operations and configuration management.
"""

__version__ = "0.1.0"
__author__ = "Cortex Team"

from .config import ConfigGenerator
from .cli import main
from .packages import PackageManager, PackageManagerType

__all__ = ["ConfigGenerator", "main", "PackageManager", "PackageManagerType"]
