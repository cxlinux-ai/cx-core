from importlib import metadata

from .cli import main
from .env_loader import load_env
from .packages import PackageManager, PackageManagerType

try:
    __version__ = metadata.version("cortex-linux")
except metadata.PackageNotFoundError:
    __version__ = "0.1.0"

__all__ = ["__version__"]
__all__ = ["main", "load_env", "PackageManager", "PackageManagerType"]
