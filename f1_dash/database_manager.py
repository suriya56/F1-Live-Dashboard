"""
Database Manager Module

Handles SQLite persistence for F1 data including seasons, events, and session results.
The session_id is a composite primary key to avoid duplicate entries.
"""

import sqlite3
import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Default database path - can be overridden via environment variable
DEFAULT_DB_PATH = os.environ.get('F1_DASH_DB_PATH', 'f1_data.db')


class DatabaseManager:
    """
    Manages SQLite database operations for F1 Dashboard data.
    
    Schema:
    - seasons: Stores available seasons (2021-2025)
    - events: Stores race events for each season
    - session_results: Stores timing data for each session (composite PK on session_id)
    """
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._init_database()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _init_database(self):
        """Initialize database tables if they don't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Seasons table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS seasons (
                    year INTEGER PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    year INTEGER NOT NULL,
                    round_number INTEGER NOT NULL,
                    event_name TEXT NOT NULL,
                    event_date TEXT,
                    country TEXT,
                    location TEXT,
                    status TEXT DEFAULT 'unknown',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (year) REFERENCES seasons(year)
                )
            """)
            
            # Session results table with composite primary key
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS session_results (
                    session_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    year INTEGER NOT NULL,
                    session_key TEXT NOT NULL,
                    session_name TEXT,
                    session_type TEXT,
                    data_json TEXT NOT NULL,
                    drivers_json TEXT,
                    columns_json TEXT,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (event_id) REFERENCES events(event_id),
                    FOREIGN KEY (year) REFERENCES seasons(year)
                )
            """)
            
            # Create indexes for faster queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_year ON events(year)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_event ON session_results(event_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_year ON session_results(year)
            """)
            
            logger.info(f"Database initialized at {self.db_path}")
    
    def save_season(self, year: int) -> bool:
        """Save a season to the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO seasons (year, updated_at)
                    VALUES (?, CURRENT_TIMESTAMP)
                """, (year,))
                return True
        except Exception as e:
            logger.error(f"Error saving season {year}: {e}")
            return False
    
    def save_seasons_batch(self, years: List[int]) -> bool:
        """Save multiple seasons in a batch."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany("""
                    INSERT OR REPLACE INTO seasons (year, updated_at)
                    VALUES (?, CURRENT_TIMESTAMP)
                """, [(y,) for y in years])
                return True
        except Exception as e:
            logger.error(f"Error saving seasons batch: {e}")
            return False
    
    def get_seasons(self) -> List[int]:
        """Get all stored seasons."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT year FROM seasons ORDER BY year DESC")
                return [row['year'] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting seasons: {e}")
            return []
    
    def save_event(self, event_data: Dict[str, Any]) -> bool:
        """Save an event to the database."""
        try:
            event_id = event_data.get('id') or f"{event_data['year']}_{event_data['round_number']}"
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO events 
                    (event_id, year, round_number, event_name, event_date, country, location, status, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    event_id,
                    event_data.get('year'),
                    event_data.get('round_number'),
                    event_data.get('event_name'),
                    event_data.get('event_date'),
                    event_data.get('country'),
                    event_data.get('location'),
                    event_data.get('status', 'unknown')
                ))
                return True
        except Exception as e:
            logger.error(f"Error saving event: {e}")
            return False
    
    def save_events_batch(self, events: List[Dict[str, Any]]) -> bool:
        """Save multiple events in a batch."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                event_tuples = []
                for event in events:
                    event_id = event.get('id') or f"{event['year']}_{event['round_number']}"
                    event_tuples.append((
                        event_id,
                        event.get('year'),
                        event.get('round_number'),
                        event.get('event_name'),
                        event.get('event_date'),
                        event.get('country'),
                        event.get('location'),
                        event.get('status', 'unknown')
                    ))
                
                cursor.executemany("""
                    INSERT OR REPLACE INTO events 
                    (event_id, year, round_number, event_name, event_date, country, location, status, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, event_tuples)
                return True
        except Exception as e:
            logger.error(f"Error saving events batch: {e}")
            return False
    
    def get_events_by_year(self, year: int) -> List[Dict[str, Any]]:
        """Get all events for a specific year."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM events WHERE year = ? ORDER BY round_number
                """, (year,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting events for year {year}: {e}")
            return []
    
    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific event by ID."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM events WHERE event_id = ?", (event_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting event {event_id}: {e}")
            return None
    
    def save_session_results(
        self, 
        session_id: str,
        event_id: str,
        year: int,
        session_key: str,
        data: List[Tuple],
        drivers: List[Tuple],
        columns: List[str],
        session_name: Optional[str] = None,
        session_type: Optional[str] = None
    ) -> bool:
        """
        Save session results to the database.
        
        Args:
            session_id: Composite key (e.g., "2023_5_R" for 2023 Round 5 Race)
            event_id: Parent event identifier
            year: Season year
            session_key: Session type key (FP1, FP2, Q, R, etc.)
            data: Session timing data as list of tuples
            drivers: List of (display_name, driver_code) tuples
            columns: Column names for the data
            session_name: Human-readable session name
            session_type: Session type classification
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO session_results 
                    (session_id, event_id, year, session_key, session_name, session_type,
                     data_json, drivers_json, columns_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    session_id,
                    event_id,
                    year,
                    session_key,
                    session_name,
                    session_type,
                    json.dumps(data),
                    json.dumps(drivers),
                    json.dumps(columns)
                ))
                return True
        except Exception as e:
            logger.error(f"Error saving session results for {session_id}: {e}")
            return False
    
    def get_session_results(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session results from the database.
        
        Returns:
            Dictionary with 'data', 'drivers', 'columns', and metadata if found, None otherwise
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM session_results WHERE session_id = ?
                """, (session_id,))
                row = cursor.fetchone()
                
                if row:
                    return {
                        'session_id': row['session_id'],
                        'event_id': row['event_id'],
                        'year': row['year'],
                        'session_key': row['session_key'],
                        'session_name': row['session_name'],
                        'session_type': row['session_type'],
                        'data': json.loads(row['data_json']),
                        'drivers': json.loads(row['drivers_json']) if row['drivers_json'] else [],
                        'columns': json.loads(row['columns_json']) if row['columns_json'] else [],
                        'fetched_at': row['fetched_at'],
                        'updated_at': row['updated_at']
                    }
                return None
        except Exception as e:
            logger.error(f"Error getting session results for {session_id}: {e}")
            return None
    
    def session_exists(self, session_id: str) -> bool:
        """Check if a session already exists in the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 1 FROM session_results WHERE session_id = ?
                """, (session_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking session existence: {e}")
            return False
    
    def get_sessions_for_event(self, event_id: str) -> List[Dict[str, Any]]:
        """Get all stored sessions for a specific event."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT session_id, session_key, session_name, session_type, updated_at
                    FROM session_results WHERE event_id = ?
                """, (event_id,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting sessions for event {event_id}: {e}")
            return []
    
    def clear_old_sessions(self, days: int = 30) -> int:
        """Clear session data older than specified days. Returns number of rows deleted."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM session_results 
                    WHERE fetched_at < datetime('now', '-{} days')
                """.format(days))
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Error clearing old sessions: {e}")
            return 0
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get statistics about the database contents."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                stats = {}
                
                cursor.execute("SELECT COUNT(*) FROM seasons")
                stats['seasons_count'] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM events")
                stats['events_count'] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM session_results")
                stats['sessions_count'] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM session_results GROUP BY year")
                stats['sessions_by_year'] = [row[0] for row in cursor.fetchall()]
                
                # Database file size
                if os.path.exists(self.db_path):
                    stats['db_size_mb'] = os.path.getsize(self.db_path) / (1024 * 1024)
                else:
                    stats['db_size_mb'] = 0
                
                return stats
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return {}


# Global instance for singleton access
db_manager = DatabaseManager()


def get_db_manager(db_path: Optional[str] = None) -> DatabaseManager:
    """Get or create a database manager instance."""
    if db_path:
        return DatabaseManager(db_path)
    return db_manager
