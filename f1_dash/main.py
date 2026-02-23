"""
Enhanced F1 Live Position Dashboard with Season Selection, SQLite Persistence, and Redis Caching

This application connects to the FastF1 API to fetch F1 session data and displays
driver standings, practice sessions, sprint races, and telemetry data in a tabbed TUI.

Features:
- Season selection (2021-2025)
- Tiered data retrieval: Redis Cache -> SQLite Database -> FastF1 API
- SQLite persistence for offline viewing
- Redis caching for fast data access
- Lazy-loading telemetry for RAM optimization
- Interactive telemetry viewer for selected drivers

Dependencies:
- fastf1, textual, matplotlib, pandas, rich, aioredis

Environment Variables:
- F1_DASH_DB_PATH: Path to SQLite database (default: f1_data.db)
- REDIS_URL: Redis connection URL (default: redis://localhost:6379)
- REDIS_TTL: Cache TTL in seconds (default: 3600)

Usage:
    python -m f1_dash.main
"""

import fastf1
import os
import sys
import logging
from rich.console import Console
from datetime import datetime, date
import pandas as pd
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, TabbedContent, TabPane, Static, Select, Button, Label
from textual.containers import Container, Horizontal, Vertical
from textual import work, on
from textual.reactive import reactive
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import asyncio
from typing import Optional, Dict, Any, List, Tuple
from contextlib import contextmanager

# Redirect stderr to suppress all library output (tracebacks, warnings, etc.)
class StderrSuppressor:
    """Suppresses stderr output from libraries that bypass logging."""
    def __init__(self):
        self.original_stderr = sys.stderr
        self.devnull = open(os.devnull, 'w')
    
    def suppress(self):
        sys.stderr = self.devnull
    
    def restore(self):
        sys.stderr = self.original_stderr
    
    def close(self):
        self.devnull.close()

# Global suppressor instance
_stderr_suppressor = StderrSuppressor()

@contextmanager
def suppress_stderr():
    """Context manager to suppress stderr output."""
    _stderr_suppressor.suppress()
    try:
        yield
    finally:
        _stderr_suppressor.restore()

# Suppress stderr during imports and initialization
_stderr_suppressor.suppress()

# Import our new modules
from .database_manager import get_db_manager, DatabaseManager
from .cache_manager import get_cache_manager, CacheManager, cache_manager

# Restore stderr for our own logging
_stderr_suppressor.restore()

# Enable the cache for FastF1
cache_path = 'fastf1_cache'
if not os.path.exists(cache_path):
    os.makedirs(cache_path)

# Clear potentially corrupted cache files
try:
    import shutil
    if os.path.exists(cache_path):
        shutil.rmtree(cache_path, ignore_errors=True)
        os.makedirs(cache_path)
except Exception:
    pass

# Suppress stderr during FastF1 cache setup
with suppress_stderr():
    fastf1.Cache.enable_cache(cache_path)
    fastf1.set_log_level(logging.ERROR)

# Initialize logging - suppress fastf1.api and fastf1.req logs
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Specifically silence fastf1 loggers and our own logger
for logger_name in ['fastf1.api', 'fastf1.req', 'fastf1.fastf1.req', 'fastf1.core', 'fastf1.fastf1.core', 'fastf1.events', 'fastf1.fastf1.events', 'f1_dash.main']:
    logging.getLogger(logger_name).setLevel(logging.ERROR)
    logging.getLogger(logger_name).propagate = False
    logging.getLogger(logger_name).addHandler(logging.NullHandler())

# Also suppress any other fastf1 sub-loggers
for logger_name in logging.root.manager.loggerDict:
    if logger_name.startswith('fastf1'):
        logging.getLogger(logger_name).setLevel(logging.ERROR)
        logging.getLogger(logger_name).propagate = False

# Initialize the console for Rich (used by Textual)
console = Console()

# Available seasons for selection (2021-2026)
AVAILABLE_SEASONS = [2026, 2025, 2024, 2023, 2022, 2021]


def get_latest_event():
    """
    Finds the most recent F1 event from the specified season's schedule.
    Returns a dictionary with event info instead of pandas Series.
    """
    try:
        year = date.today().year
        schedule = fastf1.get_event_schedule(year)

        if schedule.empty:
            return None, "Could not load the F1 event schedule for the current year."

        # Convert EventDate to datetime if it's not already
        schedule['EventDate'] = pd.to_datetime(schedule['EventDate'])
        current_date = pd.Timestamp(datetime.now())

        # First try to find an ongoing event (within 4 days)
        for idx, event in schedule.iterrows():
            event_date = event['EventDate']
            days_diff = (current_date - event_date).days
            if -1 <= days_diff <= 4:  # Event is today or within the weekend
                # Convert pandas Series to dictionary
                event_dict = {
                    'EventName': event['EventName'],
                    'EventDate': event['EventDate'],
                    'RoundNumber': event['RoundNumber'],
                    'Country': event.get('Country', 'Unknown'),
                    'Location': event.get('Location', 'Unknown')
                }
                return event_dict, None

        # If no ongoing event, get the most recent past event
        past_events = schedule[schedule['EventDate'] < current_date]
        if len(past_events) > 0:
            latest_event = past_events.iloc[-1]
            event_dict = {
                'EventName': latest_event['EventName'],
                'EventDate': latest_event['EventDate'],
                'RoundNumber': latest_event['RoundNumber'],
                'Country': latest_event.get('Country', 'Unknown'),
                'Location': latest_event.get('Location', 'Unknown')
            }
            return event_dict, None

        # If no past events, get the next upcoming event
        future_events = schedule[schedule['EventDate'] >= current_date]
        if len(future_events) > 0:
            next_event = future_events.iloc[0]
            event_dict = {
                'EventName': next_event['EventName'],
                'EventDate': next_event['EventDate'],
                'RoundNumber': next_event['RoundNumber'],
                'Country': next_event.get('Country', 'Unknown'),
                'Location': next_event.get('Location', 'Unknown')
            }
            return event_dict, None

        return None, "No events found for the current season."

    except Exception as e:
        return None, f"An error occurred while finding the latest event: {e}"

class F1Dashboard(App):
    """
    An enhanced Textual app to display F1 session data and telemetry.
    """

    CSS = """
    .telemetry-container {
        height: 20;
        border: solid $primary;
        margin: 1;
        padding: 1;
    }

    .session-info {
        height: 3;
        background: $surface;
        color: $text;
        margin: 1;
        padding: 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh Data"),
    ]

    current_event = reactive(None)
    current_session_data = reactive({})
    selected_driver = reactive(None)
    all_events = reactive([])
    current_season = reactive(2025)
    db_manager: Optional[DatabaseManager] = None
    cache_manager: Optional[CacheManager] = None
    is_loading = reactive(False)

    def __init__(self):
        super().__init__()
        self.db_manager = get_db_manager()
        self.cache_manager = cache_manager
        self._telemetry_cache = {}
        self.current_session_obj = None

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()

        with TabbedContent(initial="positions"):
            with TabPane("Positions", id="positions"):
                yield Static("Loading event data...", classes="session-info", id="event-info")
                with Container():
                    with Horizontal():
                        yield Select(
                            [(str(year), year) for year in AVAILABLE_SEASONS],
                            prompt="Select Season",
                            id="season-select",
                            value=2025
                        )
                        yield Select(
                            [("Loading events...", "loading")],
                            prompt="Select Race/Event",
                            id="event-select"
                        )
                        yield Select(
                            [("Select an event first", "none")],
                            prompt="Select Session",
                            id="session-select"
                        )
                    yield DataTable(id="positions-table")

            with TabPane("Telemetry", id="telemetry"):
                with Vertical():
                    yield Static("Select a driver from the Positions tab first", classes="session-info")
                    with Horizontal():
                        yield Select(
                            [("No driver selected", "none")],
                            prompt="Select Driver",
                            id="driver-select"
                        )
                        yield Button("Load Telemetry", id="load-telemetry")
                    yield Static("", classes="telemetry-container", id="telemetry-display")

        yield Footer()

    async def on_mount(self) -> None:
        """Called when the app is mounted. Initialize cache and load data."""
        # Initialize cache manager
        try:
            await self.cache_manager.connect()
            health = await self.cache_manager.health_check()
            logger.info(f"Cache health: {health['status']}")
        except Exception as e:
            logger.warning(f"Cache initialization failed: {e}")
        
        # Initialize database with available seasons
        self.db_manager.save_seasons_batch(AVAILABLE_SEASONS)
        
        # Load initial data
        self.load_all_events()

    def action_quit(self):
        """Action to quit the app."""
        self.exit()

    def action_refresh(self):
        """Action to refresh data."""
        self.load_all_events()

    @on(Select.Changed, "#season-select")
    def season_changed(self, event: Select.Changed) -> None:
        """Handle season selection change."""
        if event.value:
            self.current_season = event.value
            self.load_all_events()

    @work(exclusive=True, thread=True)
    def load_all_events(self):
        """Load all F1 events for the selected season using tiered retrieval."""
        try:
            self.call_from_thread(self.update_event_info, f"Loading schedule for {self.current_season}...")
            
            # Suppress stderr during FastF1 API calls
            with suppress_stderr():
                # Try cache first - but only use if data looks complete
                cached_events = self.db_manager.get_events_by_year(self.current_season)
                
                # Check if cached data is complete (F1 seasons typically have 20-24 races)
                # For current/upcoming seasons, require at least 15 races to consider cache valid
                MIN_RACES_EXPECTED = 15 if self.current_season >= 2024 else 20
                
                if cached_events and len(cached_events) >= MIN_RACES_EXPECTED:
                    events_list = self._process_events_data(cached_events, from_db=True)
                    self.all_events = events_list
                    self._update_ui_with_events(events_list)
                    return
                
                # Fallback to FastF1 API
                self.call_from_thread(self.update_event_info, f"Fetching {self.current_season} schedule from API...")
                schedule = fastf1.get_event_schedule(self.current_season)

            if schedule.empty:
                self.call_from_thread(self.update_event_info, f"Could not load F1 events for {self.current_season}")
                return

            # Convert to our format
            events_list = self._process_fastf1_schedule(schedule)
            self.all_events = events_list
            
            # Save to database (replace existing incomplete data)
            self._save_events_to_db(events_list)
            
            self._update_ui_with_events(events_list)

        except Exception as e:
            self.call_from_thread(self.update_event_info, f"Error loading events: {e}")

    @work(exclusive=True, thread=True)
    def load_event_sessions(self, event_dict):
        """Load available sessions for the selected event."""
        try:
            self.call_from_thread(self.update_event_info, f"Loading sessions for {event_dict['EventName']}...")

            # Get available sessions
            session_options = []
            session_map = {
                'FP1': 'Practice 1',
                'FP2': 'Practice 2',
                'FP3': 'Practice 3',
                'Q': 'Qualifying',
                'S': 'Sprint',
                'SS': 'Sprint Shootout',
                'R': 'Race'
            }

            # Get the year and round number
            event_year = event_dict['EventDate'].year if hasattr(event_dict['EventDate'], 'year') else self.current_season
            round_num = event_dict['RoundNumber']

            # Suppress stderr during FastF1 API calls
            with suppress_stderr():
                for session_key, session_name in session_map.items():
                    try:
                        # Try to get the event and session
                        event_obj = fastf1.get_event(event_year, round_num)
                        session = event_obj.get_session(session_key)

                        if session is not None:
                            session_options.append((session_name, session_key))
                    except Exception:
                        continue  # Session doesn't exist for this event

            if len(session_options) == 0:
                session_options = [("No sessions available", "none")]

            self.call_from_thread(self.update_session_options, session_options)
            self.call_from_thread(
                self.update_event_info,
                f"{event_dict['EventName']} | Select a session to view data"
            )

        except Exception as e:
            self.call_from_thread(self.update_event_info, f"Error loading sessions: {e}")

    @on(Select.Changed, "#event-select")
    def event_changed(self, event: Select.Changed) -> None:
        """Handle event selection change."""
        if event.value and event.value != "loading":
            # Find the selected event in our events list
            selected_event = None
            for evt in self.all_events:
                if evt['id'] == event.value:
                    selected_event = evt
                    break

            if selected_event:
                self.current_event = selected_event
                self.load_event_sessions(selected_event)

    @on(Select.Changed, "#session-select")
    def session_changed(self, event: Select.Changed) -> None:
        """Handle session selection change."""
        if event.value and event.value != "loading" and event.value != "none":
            self.load_session_data(event.value)

    @on(Select.Changed, "#driver-select")
    def driver_changed(self, event: Select.Changed) -> None:
        """Handle driver selection change."""
        if event.value and event.value != "none":
            self.selected_driver = event.value

    @on(Button.Pressed, "#load-telemetry")
    def load_telemetry_pressed(self) -> None:
        """Handle telemetry load button press."""
        if self.selected_driver and hasattr(self, 'current_session_obj'):
            self.load_telemetry_data()

    @work(exclusive=True, thread=True)
    def load_session_data(self, session_key):
        """
        Load data for the selected session using tiered retrieval:
        1. Check SQLite database
        2. Fetch from FastF1 API if not cached
        3. Save to database for future use
        """
        try:
            if self.current_event is None:
                self.call_from_thread(self.update_event_info, "No event data available.")
                return

            event_year = self.current_event['EventDate'].year if hasattr(self.current_event['EventDate'], 'year') else self.current_season
            round_num = self.current_event['RoundNumber']
            session_id = f"{event_year}_{round_num}_{session_key}"

            self.call_from_thread(self.update_event_info, "Checking for cached session data...")

            # 1. Try to load from database first
            db_session = self.db_manager.get_session_results(session_id)
            if db_session:
                logger.info(f"Loaded session {session_id} from database")
                self.call_from_thread(
                    self.update_event_info,
                    f"{self.current_event['EventName']} - {db_session.get('session_name', session_key)} | {len(db_session['data'])} drivers (from cache)"
                )
                self.call_from_thread(self.update_positions_table, db_session['data'], db_session['columns'])
                self.call_from_thread(self.update_driver_options, db_session['drivers'])
                return

            # 2. Not in database, fetch from FastF1 API
            self.call_from_thread(self.update_event_info, "Fetching session data from FastF1 API...")
            self._fetch_and_process_session(session_key, event_year, round_num)

        except Exception as e:
            # Log error without printing traceback to console (which interferes with TUI)
            self.call_from_thread(self.update_event_info, f"Session load error: {str(e)}")
            logger.error(f"Error in load_session_data: {e}")

    def _fetch_and_process_session(self, session_key: str, event_year: int, round_num: int):
        """Fetch session from FastF1 API and process the data."""
        try:
            # Suppress stderr during FastF1 API calls
            with suppress_stderr():
                event_obj = fastf1.get_event(event_year, round_num)
                session = event_obj.get_session(session_key)

                self.call_from_thread(self.update_event_info, "Loading session data from FastF1...")

                # Load only necessary data (no telemetry yet for RAM optimization)
                session.load(laps=True, telemetry=False, weather=False, messages=False)
                self.current_session_obj = session

            self.call_from_thread(self.update_event_info, "Processing session data...")

            results = session.results
            laps = session.laps if hasattr(session, 'laps') else pd.DataFrame()

            # Process the data based on session type
            data = []
            drivers = []
            columns = ["Pos", "Driver", "Team", "Best Time"]

            if session_key in ['FP1', 'FP2', 'FP3']:
                data, drivers, columns = self._process_practice_data(laps, results)
            elif session_key == 'Q':
                if len(results) > 0:
                    data, drivers, columns = self.process_qualifying_results(results)
            elif session_key == 'R':
                data, drivers, columns = self._process_race_data(laps, results)
            else:
                if len(results) > 0:
                    data, drivers, columns = self.process_session_results_safe(results, "other")

            # Update UI
            session_names = {
                'FP1': 'Practice 1', 'FP2': 'Practice 2', 'FP3': 'Practice 3',
                'Q': 'Qualifying', 'S': 'Sprint', 'SS': 'Sprint Shootout', 'R': 'Race'
            }
            session_name = session_names.get(session_key, session_key)
            event_name = self.current_event['EventName']

            if len(data) == 0:
                self.call_from_thread(
                    self.update_event_info,
                    f"{event_name} - {session_name} | No timing data found"
                )
            else:
                self.call_from_thread(
                    self.update_event_info,
                    f"{event_name} - {session_name} | {len(data)} drivers | Updated: {datetime.now().strftime('%H:%M:%S')}"
                )
                # Save to database for future use
                self._save_session_to_db(session_key, data, drivers, columns)

            self.call_from_thread(self.update_positions_table, data, columns)
            self.call_from_thread(self.update_driver_options, drivers)

        except Exception as e:
            self.call_from_thread(self.update_event_info, f"Error loading session: {e}")

    def _process_practice_data(self, laps, results):
        """Process practice session data."""
        data = []
        drivers = []

        if len(laps) > 0:
            driver_fastest_laps = {}
            for _, lap in laps.iterrows():
                if pd.isna(lap['LapTime']) or lap['LapTime'] == pd.Timedelta(0):
                    continue
                driver = lap['Driver']
                lap_time = lap['LapTime']
                if driver not in driver_fastest_laps or lap_time < driver_fastest_laps[driver]['time']:
                    driver_fastest_laps[driver] = {
                        'time': lap_time,
                        'team': lap['Team'] if 'Team' in lap else 'Unknown'
                    }

            sorted_drivers = sorted(driver_fastest_laps.items(), key=lambda x: x[1]['time'])
            for pos, (driver, info) in enumerate(sorted_drivers, 1):
                drivers.append((driver, driver))
                lap_seconds = info['time'].total_seconds()
                minutes = int(lap_seconds // 60)
                seconds = lap_seconds % 60
                formatted_time = f"{minutes:01d}:{seconds:06.3f}"
                data.append((str(pos), driver, info['team'], formatted_time))
        elif len(results) > 0:
            data, drivers, columns = self.process_session_results_safe(results, "practice")
            return data, drivers, columns

        return data, drivers, ["Pos", "Driver", "Team", "Best Time"]

    def _process_race_data(self, laps, results):
        """Process race session data."""
        data = []
        drivers = []
        columns = ["Pos", "Driver", "Team", "Last Lap", "Lap #", "Points"]

        if len(laps) > 0:
            try:
                final_laps = laps.loc[laps['IsAccurate']].drop_duplicates(subset='Driver', keep='last')
                if len(final_laps) > 0:
                    final_laps = final_laps.sort_values(by='Position')
                    for _, lap in final_laps.iterrows():
                        if pd.isna(lap['Position']):
                            continue
                        driver_pos = int(lap['Position'])
                        driver_code = lap['Driver']
                        drivers.append((driver_code, driver_code))
                        team_name = lap.get('Team', 'Unknown')
                        lap_time = lap['LapTime'].total_seconds()
                        last_lap_number = int(lap['LapNumber'])

                        driver_points = 0
                        if len(results) > 0:
                            try:
                                points_row = results[results['Abbreviation'] == driver_code]
                                if len(points_row) > 0:
                                    driver_points = int(points_row['Points'].iloc[0])
                            except:
                                pass

                        minutes = int(lap_time // 60)
                        seconds = lap_time % 60
                        formatted_time = f"{minutes:01d}:{seconds:06.3f}"
                        data.append((str(driver_pos), driver_code, team_name, formatted_time, str(last_lap_number), str(driver_points)))
            except Exception as e:
                logger.warning(f"Race lap processing error: {e}")

        if len(data) == 0 and len(results) > 0:
            data, drivers, columns = self.process_session_results_safe(results, "race")

        return data, drivers, columns

    def process_session_results_safe(self, results, session_type):
        """Safely process session results with error handling."""
        data = []
        drivers = []

        try:
            if len(results) == 0:
                if session_type == "race":
                    return [], [], ["Pos", "Driver", "Team", "Last Lap", "Lap #", "Points"]
                else:
                    return [], [], ["Pos", "Driver", "Team", "Best Time"]

            # Sort by position if available
            if 'Position' in results.columns:
                sorted_results = results.sort_values(by='Position').reset_index(drop=True)
            else:
                sorted_results = results.reset_index(drop=True)

            position_counter = 1
            for _, result in sorted_results.iterrows():
                try:
                    # Get driver identifier - try multiple columns
                    driver_code = None
                    for col in ['Abbreviation', 'Driver', 'DriverNumber']:
                        if col in result and not pd.isna(result[col]):
                            driver_code = str(result[col])
                            break

                    if not driver_code:
                        continue

                    drivers.append((driver_code, driver_code))

                    # Get position
                    if 'Position' in result and not pd.isna(result['Position']):
                        pos = int(result['Position'])
                    else:
                        pos = position_counter
                        position_counter += 1

                    # Get team
                    team_name = "Unknown"
                    for col in ['TeamName', 'Team']:
                        if col in result and not pd.isna(result[col]):
                            team_name = str(result[col])
                            break

                    if session_type == "race":
                        # Get points
                        driver_points = 0
                        if 'Points' in result and not pd.isna(result['Points']):
                            driver_points = int(result['Points'])

                        data.append((str(pos), driver_code, team_name, "N/A", "N/A", str(driver_points)))
                    else:
                        # Get best time
                        best_time = "No Time"
                        time_columns = ['Time', 'BestLapTime', 'LapTime', 'Q1', 'Q2', 'Q3']

                        for col in time_columns:
                            if col in result and not pd.isna(result[col]) and result[col] != pd.Timedelta(0):
                                try:
                                    lap_time = result[col].total_seconds()
                                    minutes = int(lap_time // 60)
                                    seconds = lap_time % 60
                                    best_time = f"{minutes:01d}:{seconds:06.3f}"
                                    break
                                except:
                                    continue

                        data.append((str(pos), driver_code, team_name, best_time))

                except Exception as e:
                    continue  # Skip this entry if there's an error

            # Return appropriate columns
            if session_type == "race":
                columns = ["Pos", "Driver", "Team", "Last Lap", "Lap #", "Points"]
            else:
                columns = ["Pos", "Driver", "Team", "Best Time"]

            return data, drivers, columns

        except Exception as e:
            # Return empty data with appropriate columns
            if session_type == "race":
                return [], [], ["Pos", "Driver", "Team", "Last Lap", "Lap #", "Points"]
            else:
                return [], [], ["Pos", "Driver", "Team", "Best Time"]

    def process_qualifying_results(self, results):
        """Special handling for qualifying results."""
        data = []
        drivers = []

        if len(results) > 0:
            results = results.sort_values(by='Position')

            for _, result in results.iterrows():
                if pd.isna(result['Position']):
                    continue

                pos = int(result['Position'])
                driver_code = result.get('Abbreviation', result.get('Driver', 'UNK'))
                drivers.append((driver_code, driver_code))
                team_name = result.get('TeamName', result.get('Team', 'Unknown'))

                # For qualifying, get the best time from Q1, Q2, Q3
                best_time = "No Time"
                for q_session in ['Q3', 'Q2', 'Q1']:  # Check Q3 first (fastest)
                    if q_session in result and not pd.isna(result[q_session]) and result[q_session] != pd.Timedelta(0):
                        lap_time = result[q_session].total_seconds()
                        minutes = int(lap_time // 60)
                        seconds = lap_time % 60
                        best_time = f"{minutes:01d}:{seconds:06.3f}"
                        break

                data.append((str(pos), driver_code, team_name, best_time))

        columns = ["Pos", "Driver", "Team", "Best Time"]
        return data, drivers, columns

    def update_event_options(self, options):
        """Update event select options."""
        event_select = self.query_one("#event-select", Select)
        event_select.set_options(options)

    def set_default_event(self, event_id):
        """Set the default selected event."""
        event_select = self.query_one("#event-select", Select)
        event_select.value = event_id

    def update_event_info(self, text: str):
        """Update the event info display."""
        event_info = self.query_one("#event-info", Static)
        event_info.update(text)

    def update_session_options(self, options):
        """Update session select options."""
        session_select = self.query_one("#session-select", Select)
        session_select.set_options(options)

    def update_positions_table(self, data, columns):
        """Update the positions table."""
        table = self.query_one("#positions-table", DataTable)
        table.clear(columns=True)
        table.add_columns(*columns)
        if data:
            table.add_rows(data)

    def update_driver_options(self, drivers):
        """Update driver select options for telemetry."""
        driver_select = self.query_one("#driver-select", Select)
        if drivers:
            driver_select.set_options(drivers)
        else:
            driver_select.set_options([("No drivers available", "none")])

    def update_telemetry_display(self, text: str):
        """Update the telemetry display."""
        telemetry_display = self.query_one("#telemetry-display", Static)
        telemetry_display.update(text)

    # ============ Helper Methods for Tiered Data Retrieval ============

    def _process_events_data(self, events_data: List[Dict], from_db: bool = False) -> List[Dict]:
        """Process event data into the format used by the UI."""
        events_list = []
        current_date = pd.Timestamp(datetime.now())

        for event in events_data:
            if from_db:
                # Convert from DB format
                event_date = pd.to_datetime(event.get('event_date'))
                event_dict = {
                    'id': event.get('event_id'),
                    'EventName': event.get('event_name'),
                    'EventDate': event_date,
                    'RoundNumber': event.get('round_number'),
                    'Country': event.get('country', 'Unknown'),
                    'Location': event.get('location', 'Unknown'),
                    'year': event.get('year')
                }
            else:
                event_dict = event

            # Determine event status
            if event_dict.get('EventDate'):
                days_diff = (current_date - pd.to_datetime(event_dict['EventDate'])).days
                if days_diff > 4:
                    status = "Completed"
                elif -1 <= days_diff <= 4:
                    status = "Current"
                else:
                    status = "Upcoming"
            else:
                status = "Unknown"

            event_dict['Status'] = status
            event_dict['DisplayName'] = f"R{event_dict['RoundNumber']}: {event_dict['EventName']} ({status})"
            events_list.append(event_dict)

        events_list.sort(key=lambda x: x['RoundNumber'])
        return events_list

    def _process_fastf1_schedule(self, schedule: pd.DataFrame) -> List[Dict]:
        """Convert FastF1 schedule DataFrame to our event format."""
        events_list = []
        current_date = pd.Timestamp(datetime.now())

        for idx, event in schedule.iterrows():
            event_date = pd.to_datetime(event['EventDate'])
            event_id = f"{event['RoundNumber']}_{event['EventName'].replace(' ', '_')}"

            days_diff = (current_date - event_date).days
            if days_diff > 4:
                status = "Completed"
            elif -1 <= days_diff <= 4:
                status = "Current"
            else:
                status = "Upcoming"

            event_dict = {
                'id': event_id,
                'EventName': event['EventName'],
                'EventDate': event_date,
                'RoundNumber': event['RoundNumber'],
                'Country': event.get('Country', 'Unknown'),
                'Location': event.get('Location', 'Unknown'),
                'Status': status,
                'DisplayName': f"R{event['RoundNumber']}: {event['EventName']} ({status})",
                'year': self.current_season
            }
            events_list.append(event_dict)

        events_list.sort(key=lambda x: x['RoundNumber'])
        return events_list

    def _save_events_to_db(self, events_list: List[Dict]):
        """Save events to the database for future use."""
        try:
            db_events = []
            for event in events_list:
                db_events.append({
                    'id': event['id'],
                    'year': self.current_season,
                    'round_number': event['RoundNumber'],
                    'event_name': event['EventName'],
                    'event_date': str(event['EventDate']),
                    'country': event.get('Country', 'Unknown'),
                    'location': event.get('Location', 'Unknown'),
                    'status': event.get('Status', 'unknown')
                })
            self.db_manager.save_events_batch(db_events)
            logger.info(f"Saved {len(db_events)} events to database")
        except Exception as e:
            logger.warning(f"Failed to save events to database: {e}")

    def _update_ui_with_events(self, events_list: List[Dict]):
        """Update the UI with the loaded events."""
        # Create options for the event selector
        event_options = [(evt['DisplayName'], evt['id']) for evt in events_list]

        # Find current or most recent event to select by default
        default_event = None
        for evt in events_list:
            if evt['Status'] == 'Current':
                default_event = evt
                break

        if not default_event:
            completed_events = [evt for evt in events_list if evt['Status'] == 'Completed']
            if completed_events:
                default_event = completed_events[-1]

        if not default_event and events_list:
            default_event = events_list[0]

        self.call_from_thread(self.update_event_options, event_options)

        if default_event:
            self.current_event = default_event
            self.call_from_thread(self.set_default_event, default_event['id'])
            self.load_event_sessions(default_event)
        else:
            self.call_from_thread(
                self.update_event_info,
                f"Season {self.current_season} schedule loaded - select an event to view sessions"
            )

    def _save_session_to_db(self, session_key: str, data: List[Tuple], drivers: List[Tuple], columns: List[str]):
        """Save session results to the database."""
        try:
            if not self.current_event:
                return

            session_id = f"{self.current_season}_{self.current_event['RoundNumber']}_{session_key}"
            event_id = self.current_event['id']

            session_names = {
                'FP1': 'Practice 1', 'FP2': 'Practice 2', 'FP3': 'Practice 3',
                'Q': 'Qualifying', 'S': 'Sprint', 'SS': 'Sprint Shootout', 'R': 'Race'
            }

            self.db_manager.save_session_results(
                session_id=session_id,
                event_id=event_id,
                year=self.current_season,
                session_key=session_key,
                data=data,
                drivers=drivers,
                columns=columns,
                session_name=session_names.get(session_key, session_key),
                session_type=self._get_session_type(session_key)
            )
            logger.debug(f"Saved session {session_id} to database")
        except Exception as e:
            logger.warning(f"Failed to save session to database: {e}")

    def _get_session_type(self, session_key: str) -> str:
        """Get the session type classification."""
        if session_key in ['FP1', 'FP2', 'FP3']:
            return 'practice'
        elif session_key == 'Q':
            return 'qualifying'
        elif session_key in ['S', 'SS']:
            return 'sprint'
        elif session_key == 'R':
            return 'race'
        return 'other'

    # ============ Lazy-Loading Telemetry Methods ============

    def _get_lazy_telemetry_data(self, driver_code: str, lap_number: Optional[int] = None) -> Dict[str, Any]:
        """
        Lazy-load telemetry data - only fetch specific data points needed for UI.
        """
        try:
            if not hasattr(self, 'current_session_obj') or self.current_session_obj is None:
                logger.warning("No session object available for telemetry")
                return {'error': 'No session loaded'}

            session = self.current_session_obj

            # Check cache first
            cache_key = f"{self.current_season}_{self.current_event['RoundNumber']}_{driver_code}"
            if cache_key in self._telemetry_cache:
                logger.debug(f"Returning cached telemetry for {driver_code}")
                return self._telemetry_cache[cache_key]

            # Check if session has laps loaded
            if not hasattr(session, 'laps') or session.laps is None or len(session.laps) == 0:
                logger.warning("Session has no lap data")
                return {'error': 'No lap data in session'}

            driver_laps = session.laps[session.laps['Driver'] == driver_code]

            if len(driver_laps) == 0:
                logger.warning(f"No laps found for driver {driver_code}")
                return {'error': f'No laps found for driver {driver_code}'}

            # Get fastest lap
            try:
                target_lap = driver_laps.pick_fastest()
            except Exception as e:
                logger.warning(f"Error picking fastest lap: {e}")
                # Fallback to first lap
                target_lap = driver_laps.iloc[0] if len(driver_laps) > 0 else None

            if target_lap is None or (hasattr(target_lap, 'empty') and target_lap.empty):
                return {'error': 'No valid lap data'}

            # Get telemetry - this may require loading telemetry data
            try:
                # Load telemetry if not already loaded
                if not hasattr(session, '_telemetry_loaded') or not session._telemetry_loaded:
                    logger.info("Loading telemetry data from FastF1...")
                    session.load(telemetry=True, weather=False, messages=False, laps=False)
                    session._telemetry_loaded = True

                telemetry = target_lap.get_telemetry()
            except Exception as e:
                logger.warning(f"Error getting telemetry: {e}")
                # Return basic lap info without telemetry
                telemetry_summary = {
                    'driver': driver_code,
                    'lap_number': int(target_lap['LapNumber']) if 'LapNumber' in target_lap else None,
                    'lap_time_seconds': target_lap['LapTime'].total_seconds() if hasattr(target_lap['LapTime'], 'total_seconds') else 0,
                    'compound': target_lap.get('Compound', 'Unknown'),
                    'max_speed': 0,
                    'avg_speed': 0,
                    'max_throttle': 0,
                    'max_brake': 0,
                    'data_points': 0,
                    'note': 'Telemetry data unavailable - showing lap time only'
                }
                self._telemetry_cache[cache_key] = telemetry_summary
                return telemetry_summary

            if telemetry is None or len(telemetry) == 0:
                return {'error': 'Empty telemetry data'}

            # Extract data points
            try:
                max_speed = float(telemetry['Speed'].max()) if 'Speed' in telemetry.columns else 0
                avg_speed = float(telemetry['Speed'].mean()) if 'Speed' in telemetry.columns else 0
                max_throttle = float(telemetry['Throttle'].max()) if 'Throttle' in telemetry.columns else 0
                max_brake = float(telemetry['Brake'].max()) if 'Brake' in telemetry.columns else 0
            except Exception as e:
                logger.warning(f"Error extracting telemetry values: {e}")
                max_speed = avg_speed = max_throttle = max_brake = 0

            telemetry_summary = {
                'driver': driver_code,
                'lap_number': int(target_lap['LapNumber']) if 'LapNumber' in target_lap else None,
                'lap_time_seconds': target_lap['LapTime'].total_seconds() if hasattr(target_lap['LapTime'], 'total_seconds') else 0,
                'compound': target_lap.get('Compound', 'Unknown'),
                'max_speed': max_speed,
                'avg_speed': avg_speed,
                'max_throttle': max_throttle,
                'max_brake': max_brake,
                'data_points': len(telemetry)
            }

            self._telemetry_cache[cache_key] = telemetry_summary
            return telemetry_summary

        except Exception as e:
            logger.error(f"Error in lazy telemetry loading: {e}", exc_info=True)
            return {'error': str(e)}

    def _format_telemetry_summary(self, telemetry_data: Dict[str, Any]) -> str:
        """Format telemetry data for display."""
        if not telemetry_data:
            return "No telemetry data available."

        # Check for error
        if 'error' in telemetry_data:
            return f"Telemetry Error: {telemetry_data['error']}"

        lap_time = telemetry_data.get('lap_time_seconds', 0)
        minutes = int(lap_time // 60)
        seconds = lap_time % 60
        formatted_time = f"{minutes:01d}:{seconds:06.3f}"

        note = telemetry_data.get('note', '')

        result = f"""Driver: {telemetry_data.get('driver', 'Unknown')}
Fastest Lap Time: {formatted_time}
Max Speed: {telemetry_data.get('max_speed', 0):.1f} km/h
Average Speed: {telemetry_data.get('avg_speed', 0):.1f} km/h
Max Throttle: {telemetry_data.get('max_throttle', 0):.1f}%
Max Brake: {telemetry_data.get('max_brake', 0):.1f}%
Lap Number: {telemetry_data.get('lap_number', 'Unknown')}
Compound: {telemetry_data.get('compound', 'Unknown')}""".strip()

        if note:
            result += f"\n\nNote: {note}"

        return result

    @work(exclusive=True, thread=True)
    def load_telemetry_data(self):
        """Load telemetry data using lazy-loading for RAM optimization."""
        try:
            if not self.selected_driver:
                self.call_from_thread(self.update_telemetry_display, "No driver selected.")
                return

            self.call_from_thread(self.update_telemetry_display, "Loading telemetry data...")

            # Use lazy-loading to get only required data points
            telemetry_data = self._get_lazy_telemetry_data(self.selected_driver)

            # Format and display - even if empty/error
            telemetry_info = self._format_telemetry_summary(telemetry_data)
            self.call_from_thread(self.update_telemetry_display, telemetry_info)

        except Exception as e:
            logger.error(f"Error in load_telemetry_data: {e}", exc_info=True)
            self.call_from_thread(self.update_telemetry_display, f"Error loading telemetry: {e}")

def main():
    """Entry point for the f1-dash application."""
    app = F1Dashboard()
    app.run()

if __name__ == "__main__":
    main()
