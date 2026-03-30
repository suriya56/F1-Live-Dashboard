# F1 Dashboard - Development Documentation

## Project Overview

**F1 Dashboard** is a terminal-based user interface (TUI) application that connects to the FastF1 API to fetch and display Formula 1 session data. It provides real-time position tracking, race results viewing across multiple seasons, and interactive telemetry comparison.

### Core Goals

1. **Live Race Tracking** - Real-time position updates during F1 race weekends
2. **Season Archive** - Browse race results from current and previous seasons (last 3 years)
3. **Offline Support** - Cache race results locally for offline viewing
4. **PyPI Distribution** - Easy installation via pip for end users

---

## Architecture

### Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| UI Framework | Textual | Terminal user interface |
| Data Source | FastF1 API | F1 session data |
| Data Processing | Pandas | Data manipulation |
| Local Storage | SQLite | Season archive caching |
| Cross-platform Paths | platformdirs | User data directory |
| Visualization | Matplotlib | Telemetry charts |
| Rich Output | Rich | Terminal formatting |

### Project Structure

```
f1-dash/
├── f1_dash/              # Main package
│   ├── __init__.py      # Package init with version
│   └── main.py          # Core application (1200+ lines)
├── docs/                # Design specs and plans
├── pyproject.toml       # Modern package config
├── setup.py             # Legacy setup config
├── requirements.txt     # Dependencies
├── LICENSE             # MIT License
└── MANIFEST.in         # Package manifest
```

### Key Design Patterns

**1. Reactive State Management (Textual)**
- Uses `reactive` attributes for automatic UI updates
- Changes to reactive values trigger widget refreshes

**2. Background Workers (Textual @work)**
- Heavy operations run in background threads
- Prevents UI blocking during API calls
- Uses `call_from_thread` to update UI from worker threads

**3. Tiered Data Retrieval**
- Live sessions: Real-time API polling
- Recent races: FastF1 API
- Older races: Local SQLite cache

**4. Graceful Error Handling**
- All API calls wrapped in try/except
- Fallback to cached data if API fails
- User-friendly error messages in UI

---

## Features Implementation

### 1. Live Race Tracking

**How it works:**
1. User navigates to "Live" tab
2. App loads current event's race session
3. Loads lap data with `session.load(laps=True)`
4. Polls for updates every 30 seconds
5. Displays real-time positions

**Key code location:** `f1_dash/main.py:843-950`

### 2. Season Archive

**How it works:**
1. Year dropdown shows last 3 seasons (current year ± 2)
2. Selecting a year loads that season's event schedule
3. Each event shows status: Current, Completed, Upcoming
4. Race results auto-save to SQLite on first view
5. Subsequent views load from local cache

**Database schema:**
```sql
CREATE TABLE race_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    event_name TEXT NOT NULL,
    round_number INTEGER,
    position INTEGER,
    driver_code TEXT,
    team_name TEXT,
    points REAL,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(year, event_name, driver_code)
)
```

**Storage location:** Platform-appropriate user data directory
- Windows: `%LOCALAPPDATA%\f1-dash\f1-dash\seasons.db`
- Linux: `~/.local/share/f1-dash/seasons.db`
- macOS: `~/Library/Application Support/f1-dash/seasons.db`

**Key code location:** `f1_dash/main.py:145-230`

### 3. Telemetry Viewer

**How it works:**
1. User selects a driver from Positions tab
2. Navigates to Telemetry tab
3. Clicks "Load Telemetry"
4. App fetches lap-by-lap data for that driver
5. Displays fastest lap comparison chart

**Key code location:** `f1_dash/main.py:760-840`

---

## Development Process

### Workflow

1. **Brainstorming** - Design features before implementation
2. **Specification** - Document requirements in `docs/superpowers/specs/`
3. **Planning** - Create task breakdown in `docs/superpowers/plans/`
4. **Implementation** - Use subagent-driven-development for tasks
5. **Verification** - Test imports and basic functionality
6. **PyPI Upload** - Build and publish to PyPI
7. **GitHub Push** - Commit with proper excludes

### PyPI Deployment Checklist

1. Update version in:
   - `f1_dash/__init__.py`
   - `setup.py`

2. Build package:
   ```bash
   python -m build
   ```

3. Upload to PyPI:
   ```bash
   twine upload dist/*
   ```

4. Verify:
   ```bash
   pip install f1-dash
   f1-dash
   ```

### File Exclusions (.gitignore)

The following are excluded from GitHub but needed for local development:
- `.agents/` - AI agent skills
- `f1.py` - Local test file
- `fastf1_cache/` - API cache
- `*.db` - SQLite databases
- `docs/` - Design documents

---

## Key Implementation Details

### Imports and Dependencies

**Core imports:**
```python
import fastf1           # F1 data API
import textual          # TUI framework
import pandas           # Data processing
import sqlite3          # Local database
import platformdirs     # Cross-platform paths
import matplotlib      # Charts
import rich            # Terminal formatting
```

### Entry Point

The package exposes a CLI command via `pyproject.toml`:
```toml
[project.scripts]
f1-dash = "f1_dash.main:main"
```

### Version Management

Using setuptools_scm for automatic version inference from git tags:
- Version scheme: `guess-next-dev`
- Local scheme: `dirty-tag`

Manual version override in `__init__.py` for stable releases.

---

## Working Principles

### 1. Graceful Degradation

Always provide fallback when primary method fails:
- API fails → Show cached data
- Cache missing → Show error message
- No live race → Display "No live session available"

### 2. Background Processing

All network operations must run in background:
```python
@work(exclusive=True, thread=True)
def load_session_data(self, session_key):
    # Heavy operation here
    self.call_from_thread(self.update_ui, data)
```

### 3. Cross-Platform Compatibility

Use `platformdirs` for user data paths:
```python
data_dir = platformdirs.user_data_dir("f1-dash")
```

### 4. Minimal Dependencies

Keep dependencies to essential packages only:
- fastf1 - Required for F1 data
- textual - Required for TUI
- pandas, matplotlib, rich - Required for data/charts

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| No live session | Expected when no race weekend - check FastF1 schedule |
| Import errors | Run `pip install -r requirements.txt` |
| Cache issues | Delete `fastf1_cache/` folder |
| Permission errors | Check user data directory permissions |

### Debug Mode

Add logging to understand what's happening:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## Future Enhancements

Potential improvements for future versions:

1. **Multiple Series Support** - F2, F3, etc.
2. **Team Radio** - Audio playback
3. **Weather Data** - Rain predictions
4. **Driver Stats** - Career statistics
5. **Dark/Light Theme** - Color customization

---

## License

MIT License - See LICENSE file for details.

## Credits

- FastF1 team for the excellent API
- Textual team for the powerful TUI framework
- All contributors and users
