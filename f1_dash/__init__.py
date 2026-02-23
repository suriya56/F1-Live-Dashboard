"""
F1 Dashboard - An enhanced F1 Live Position Dashboard with telemetry data.
"""

__version__ = "0.2.1"

from .main import main, F1Dashboard, AVAILABLE_SEASONS
from .database_manager import DatabaseManager, get_db_manager
from .cache_manager import CacheManager, get_cache_manager

__all__ = ["main", "F1Dashboard", "AVAILABLE_SEASONS", "DatabaseManager", "get_db_manager", "CacheManager", "get_cache_manager"]
