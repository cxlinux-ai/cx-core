"""
Intelligent Tutor - AI-Powered Installation Tutor for Cortex Linux.

An interactive AI tutor that teaches users about packages and best practices.
"""

__version__ = "0.1.0"
__author__ = "Sri Krishna Vamsi"

from cortex.tutor.branding import console, tutor_print
from cortex.tutor.config import Config

__all__ = ["Config", "console", "tutor_print", "__version__"]
