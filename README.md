# F1 Dashboard

An enhanced F1 Live Position Dashboard with telemetry data visualization.

This script connects to the FastF1 API to fetch live session data for F1 events and displays driver standings, practice sessions, sprint races, and telemetry data in a tabbed terminal user interface (TUI).

## Features

- **Season Archive** - Browse race results from current and previous seasons (last 3 years)
- **Live Race Tracking** - Real-time position updates during race weekends
- **View all session types** - FP1, FP2, FP3, Sprint, Qualifying, Race
- **Interactive telemetry viewer** - Compare lap times between drivers
- **Session switching** - Select any event from any available season
- **Offline support** - Previously viewed race results are cached locally

## Installation

You can install f1-dash using pip:

```bash
pip install f1-dash
```

Or using uv:

```bash
uv pip install f1-dash
```

## Usage

After installation, you can run the dashboard with:

```bash
f1-dash
```

The TUI can be exited by pressing `Ctrl+C` or `q`.

### Navigation

- Use arrow keys to navigate between dropdowns
- Press Enter to select
- Press `r` to refresh data
- Press `q` to quit

## Requirements

- Python 3.8 or higher
- fastf1
- textual
- pandas
- rich
- matplotlib

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.