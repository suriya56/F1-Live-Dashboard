"""
Enhanced F1 Live Position Dashboard

This script connects to the FastF1 API to fetch live session data for the most
recent F1 event and displays driver standings, practice sessions, sprint races,
and telemetry data in a tabbed terminal user interface (TUI).

Features:
- View all session types (FP1, FP2, FP3, Sprint, Qualifying, Race)
- Interactive telemetry viewer for selected drivers
- Real-time position updates
- Session switching capability

Dependencies:
- fastf1 (pip install fastf1)
- textual (pip install textual)
- matplotlib (pip install matplotlib)
- pandas (pip install pandas)

Usage:
1. Make sure you have the dependencies installed.
2. Run the script from your terminal: python f1_dashboard.py
   Note: On some systems, you might need to use `python3` instead of `python`.
   The TUI can be exited by pressing Ctrl+C or q.
"""

import fastf1
import os
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

# Enable the cache for FastF1
cache_path = 'fastf1_cache'
if not os.path.exists(cache_path):
    os.makedirs(cache_path)

fastf1.Cache.enable_cache(cache_path)

# Suppress the verbose logging from FastF1
fastf1.set_log_level(logging.ERROR)

# Initialize the console for Rich (used by Textual)
console = Console()

def get_latest_event():
    """
    Finds the most recent F1 event from the current season's schedule.
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

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()

        with TabbedContent(initial="positions"):
            with TabPane("Positions", id="positions"):
                yield Static("Loading event data...", classes="session-info", id="event-info")
                with Container():
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

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        self.load_all_events()

    def action_quit(self):
        """Action to quit the app."""
        self.exit()

    def action_refresh(self):
        """Action to refresh data."""
        self.load_all_events()

    @work(exclusive=True, thread=True)
    def load_all_events(self):
        """Load all F1 events for the current season."""
        try:
            year = date.today().year
            schedule = fastf1.get_event_schedule(year)

            if schedule.empty:
                self.call_from_thread(self.update_event_info, "Could not load F1 events for current season")
                return

            # Convert schedule to list of event dictionaries
            events_list = []
            current_date = pd.Timestamp(datetime.now())

            for idx, event in schedule.iterrows():
                event_date = pd.to_datetime(event['EventDate'])

                # Create a unique ID for each event
                event_id = f"{event['RoundNumber']}_{event['EventName'].replace(' ', '_')}"

                # Determine event status
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
                    'EventDate': event['EventDate'],
                    'RoundNumber': event['RoundNumber'],
                    'Country': event.get('Country', 'Unknown'),
                    'Location': event.get('Location', 'Unknown'),
                    'Status': status,
                    'DisplayName': f"R{event['RoundNumber']}: {event['EventName']} ({status})"
                }
                events_list.append(event_dict)

            # Sort events by round number
            events_list.sort(key=lambda x: x['RoundNumber'])
            self.all_events = events_list

            # Create options for the event selector
            event_options = [(evt['DisplayName'], evt['id']) for evt in events_list]

            # Find current or most recent event to select by default
            default_event = None
            for evt in events_list:
                if evt['Status'] == 'Current':
                    default_event = evt
                    break

            if not default_event:
                # No current event, find most recent completed
                completed_events = [evt for evt in events_list if evt['Status'] == 'Completed']
                if completed_events:
                    default_event = completed_events[-1]

            if not default_event and events_list:
                # Fallback to first event
                default_event = events_list[0]

            self.call_from_thread(self.update_event_options, event_options)

            if default_event:
                self.current_event = default_event
                self.call_from_thread(self.set_default_event, default_event['id'])
                self.load_event_sessions(default_event)
            else:
                self.call_from_thread(self.update_event_info, f"Season {year} schedule loaded - select an event to view sessions")

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
            event_year = event_dict['EventDate'].year if hasattr(event_dict['EventDate'], 'year') else date.today().year
            round_num = event_dict['RoundNumber']

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
        """Load data for the selected session."""
        try:
            # Check if current_event is None or empty
            if self.current_event is None:
                self.call_from_thread(self.update_event_info, "No event data available.")
                return

            self.call_from_thread(self.update_event_info, "Loading session data...")

            # Get event object using year and round number from our dictionary
            event_year = self.current_event['EventDate'].year if hasattr(self.current_event['EventDate'], 'year') else date.today().year
            round_num = self.current_event['RoundNumber']

            try:
                event_obj = fastf1.get_event(event_year, round_num)
                session = event_obj.get_session(session_key)

                # Load the session data properly - this is the key fix!
                self.call_from_thread(self.update_event_info, "Loading session data from FastF1...")

                # For practice sessions, we mainly need lap times and results
                if session_key in ['FP1', 'FP2', 'FP3']:
                    session.load(laps=True, telemetry=False, weather=False, messages=False)
                # For qualifying, we need results and potentially laps
                elif session_key == 'Q':
                    session.load(laps=True, telemetry=False, weather=False, messages=False)
                # For race, we need everything
                elif session_key == 'R':
                    session.load(laps=True, telemetry=False, weather=False, messages=False)
                # For sprint sessions
                else:
                    session.load(laps=True, telemetry=False, weather=False, messages=False)

                self.current_session_obj = session  # Store for telemetry use

            except Exception as e:
                self.call_from_thread(self.update_event_info, f"Error loading session: {e}")
                return

            self.call_from_thread(self.update_event_info, "Processing session data...")

            # Now try to get the data
            try:
                results = session.results
                laps = session.laps if hasattr(session, 'laps') else pd.DataFrame()

                # Debug info
                debug_info = f"Results: {len(results)} rows"
                if len(results) > 0:
                    debug_info += f", Columns: {list(results.columns)[:8]}"  # Show first 8 columns
                debug_info += f" | Laps: {len(laps)} rows"

                self.call_from_thread(self.update_event_info, f"Debug: {debug_info}")

            except Exception as e:
                self.call_from_thread(self.update_event_info, f"Error accessing session data: {e}")
                return

            # Process the data based on session type
            data = []
            drivers = []
            columns = ["Pos", "Driver", "Team", "Best Time"]  # Default columns

            if session_key in ['FP1', 'FP2', 'FP3']:
                # For practice sessions, use lap times
                if len(laps) > 0:
                    # Get fastest lap for each driver
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

                    # Sort drivers by fastest lap time
                    sorted_drivers = sorted(driver_fastest_laps.items(), key=lambda x: x[1]['time'])

                    for pos, (driver, info) in enumerate(sorted_drivers, 1):
                        drivers.append((driver, driver))

                        # Format time
                        lap_seconds = info['time'].total_seconds()
                        minutes = int(lap_seconds // 60)
                        seconds = lap_seconds % 60
                        formatted_time = f"{minutes:01d}:{seconds:06.3f}"

                        data.append((str(pos), driver, info['team'], formatted_time))

                elif len(results) > 0:
                    # Fallback to results if no lap data
                    data, drivers, columns = self.process_session_results_safe(results, "practice")

            elif session_key == 'Q':
                # For qualifying, use results which should have Q1, Q2, Q3 times
                if len(results) > 0:
                    data, drivers, columns = self.process_qualifying_results(results)

            elif session_key == 'R':
                # For race, prefer lap data but fallback to results
                if len(laps) > 0:
                    try:
                        # Get final race positions
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

                                # Get points from results
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

                            columns = ["Pos", "Driver", "Team", "Last Lap", "Lap #", "Points"]
                    except Exception as e:
                        self.call_from_thread(self.update_event_info, f"Race lap processing error: {e}")

                if len(data) == 0 and len(results) > 0:
                    # Fallback to results
                    data, drivers, columns = self.process_session_results_safe(results, "race")

            else:
                # Sprint or other sessions
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

            self.call_from_thread(self.update_positions_table, data, columns)
            self.call_from_thread(self.update_driver_options, drivers)

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self.call_from_thread(self.update_event_info, f"Session load error: {str(e)}")

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

    @work(exclusive=True, thread=True)
    def load_telemetry_data(self):
        """Load telemetry data for the selected driver."""
        try:
            if not hasattr(self, 'current_session_obj') or not self.selected_driver:
                return

            self.call_from_thread(self.update_telemetry_display, "Loading telemetry data...")

            # Load telemetry
            session = self.current_session_obj
            session.load(telemetry=True, weather=False)

            # Get driver laps
            driver_laps = session.laps[session.laps['Driver'] == self.selected_driver]

            if len(driver_laps) == 0:
                self.call_from_thread(self.update_telemetry_display, "No telemetry data available for this driver.")
                return

            # Get fastest lap
            fastest_lap = driver_laps.pick_fastest()

            if fastest_lap is None or (hasattr(fastest_lap, 'empty') and fastest_lap.empty):
                self.call_from_thread(self.update_telemetry_display, "No valid lap data found for this driver.")
                return

            # Get telemetry for fastest lap
            telemetry = fastest_lap.get_telemetry()

            if len(telemetry) == 0:
                self.call_from_thread(self.update_telemetry_display, "No telemetry data available for fastest lap.")
                return

            # Create telemetry summary
            max_speed = telemetry['Speed'].max()
            avg_speed = telemetry['Speed'].mean()
            max_throttle = telemetry['Throttle'].max()
            max_brake = telemetry['Brake'].max() if 'Brake' in telemetry.columns else 0

            lap_time = fastest_lap['LapTime'].total_seconds()
            minutes = int(lap_time // 60)
            seconds = lap_time % 60
            formatted_time = f"{minutes:01d}:{seconds:06.3f}"

            telemetry_info = f"""
Driver: {self.selected_driver}
Fastest Lap Time: {formatted_time}
Max Speed: {max_speed:.1f} km/h
Average Speed: {avg_speed:.1f} km/h
Max Throttle: {max_throttle:.1f}%
Max Brake: {max_brake:.1f}%
Lap Number: {fastest_lap['LapNumber']}
Compound: {fastest_lap['Compound']}
            """.strip()

            self.call_from_thread(self.update_telemetry_display, telemetry_info)

        except Exception as e:
            self.call_from_thread(self.update_telemetry_display, f"Error loading telemetry: {e}")

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

def main():
    """Entry point for the f1-dash application."""
    app = F1Dashboard()
    app.run()

if __name__ == "__main__":
    main()
