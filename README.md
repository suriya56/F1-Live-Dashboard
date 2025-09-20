# F1 Dashboard

An enhanced F1 Live Position Dashboard with telemetry data visualization.

This script connects to the FastF1 API to fetch live session data for the most recent F1 event and displays driver standings, practice sessions, sprint races, and telemetry data in a tabbed terminal user interface (TUI).

## Features

- View all session types (FP1, FP2, FP3, Sprint, Qualifying, Race)
- Interactive telemetry viewer for selected drivers
- Real-time position updates
- Session switching capability
- Event selection from the entire season

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

## Requirements

- Python 3.8 or higher
- fastf1
- textual
- pandas
- rich
- matplotlib

## License

This project is licensed under the MIT License - see the LICENSE file for details.