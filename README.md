# F1 Dashboard

An enhanced F1 Live Position Dashboard with SQLite persistence, Redis caching, and telemetry data visualization.

## Features

- **Season Selection**: Choose from seasons 2021-2026
- **Session Types**: View FP1, FP2, FP3, Sprint, Qualifying, and Race sessions
- **SQLite Persistence**: Offline data storage for previously loaded sessions
- **Redis Caching**: Fast data retrieval with cache-aside pattern
- **Lazy-loading Telemetry**: RAM-optimized telemetry viewing for selected drivers
- **Interactive TUI**: Built with Textual for a modern terminal interface

## Installation

### From PyPI (Recommended)

```bash
pip install f1-dash
```

### From Source

```bash
git clone https://github.com/suriya56/F1-Live-Dashboard.git
cd f1-dash
pip install .
```

## Usage

Run the dashboard:

```bash
f1-dash
```

### Controls

- **q** - Quit the application
- **r** - Refresh data
- **Tab** - Switch between Positions and Telemetry tabs

### Features

1. **Select Season**: Choose a season from 2021-2026
2. **Select Event**: Pick a Grand Prix from the dropdown
3. **Select Session**: Choose from available sessions (Practice, Qualifying, Race)
4. **View Telemetry**: Go to Telemetry tab, select a driver, and click "Load Telemetry"

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `F1_DASH_DB_PATH` | Path to SQLite database | `f1_data.db` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379` |
| `REDIS_TTL` | Cache TTL in seconds | `3600` |

## Optional: Redis Setup

For enhanced caching performance, install and run Redis:

```bash
# Docker
docker run -d -p 6379:6379 redis:latest

# Or install locally
# Ubuntu/Debian: sudo apt install redis-server
# macOS: brew install redis && brew services start redis
```

The app works without Redis (uses memory cache fallback).

## Requirements

- Python 3.8 or higher
- fastf1 >= 3.0.0
- textual >= 0.40.0
- pandas >= 1.5.0
- rich >= 13.0.0
- matplotlib >= 3.5.0
- aioredis >= 2.0.0 (optional, for Redis caching)
- redis >= 4.0.0 (optional, for Redis caching)

## Architecture

The app uses a **tiered data retrieval** system:
1. **Redis Cache** - Fastest, 3600s TTL
2. **SQLite Database** - Persistent local storage
3. **FastF1 API** - Live data from Ergast/F1

Data flows: API → SQLite → Redis → UI

## Changelog

### v0.2.0 (2025-02-23)
- Added season selection (2021-2026)
- Added SQLite persistence layer
- Added Redis caching with cache-aside pattern
- Implemented lazy-loading telemetry for RAM optimization
- Suppressed library logging for clean TUI

### v0.1.0 (Initial Release)
- Basic F1 dashboard with FastF1 API integration
- Telemetry viewer
- Session switching
