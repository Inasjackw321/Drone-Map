# Drone & Missile Tracker - Usage Guide

## Quick Start

### 1. View the Map

Open `index.html` in a web browser to see the interactive map with drone and missile tracking.

The map auto-refreshes every 10 seconds and displays:
- 🛸 Yellow markers for drones
- 🚀 Red markers for missiles
- Alert zones around major cities
- Real-time threat statistics
- Proximity alerts

### 2. Start Automated Tracking

Run the automated service to continuously update tracking data:

```bash
./start_tracking.sh
```

Or manually:

```bash
python3 auto_update_service.py
```

The service will:
- Update data every 60 seconds
- Use test data by default (no Telegram credentials needed)
- Automatically switch to real Telegram data when configured
- Log all updates with timestamps

## Data Sources

### Test Data (Default)

The system uses realistic test data by default. To generate new test data manually:

```bash
python3 test_data.py
```

This creates random drone and missile sightings around major Ukrainian cities.

### Real Telegram Data (Optional)

To use real Telegram channel data:

1. **Get Telegram API credentials** from https://my.telegram.org
2. **Configure the scraper**:
   ```bash
   python3 telegram-scraper.py
   ```
   - Enter your API ID and API Hash
   - Authenticate with QR code or phone number
   - Select channels to monitor

3. **The automated service will detect** the configuration and automatically:
   - Process Telegram data from channels
   - Extract coordinates and threat information
   - Update the map with real sightings

## Files & Components

### Main Files

- **`index.html`** - Interactive map interface (open in browser)
- **`drone_data.json`** - Current tracking data (auto-updated)
- **`auto_update_service.py`** - Automated update service
- **`start_tracking.sh`** - Start script for the service

### Data Collection

- **`telegram-scraper.py`** - Scrape Telegram channels for drone alerts
- **`process_scraped_data.py`** - Extract coordinates from Telegram messages
- **`test_data.py`** - Generate realistic test data

### Configuration

- **`state.json`** - Telegram scraper configuration (auto-created)
- **`.env`** - Environment variables (copy from `.env.example`)

## Map Features

### Display

- **Markers**: Yellow (drones) and Red (missiles) with pulsing animation
- **Alert Zones**: 50km circles around major cities
- **Popups**: Click markers for detailed threat information

### HUD (Heads-Up Display)

- **Statistics**: Real-time count of drones, missiles, and total threats
- **Alerts**: Proximity warnings for threats within 100km of major cities
- **Active Threats**: List of recent sightings

### Status Bar

- Last update timestamp
- System time
- Connection status

## Channels Monitored

When Telegram is configured, these channels are monitored:

1. **kpszsu** - Main Ukrainian air defense updates
2. **air_alert_ua** - Air alert notifications
3. **ukraine_now_english** - English language updates
4. **nexta_live** - Breaking news
5. **uniannet** - UNIAN news agency
6. **tchuky** - Regional alerts

## How It Works

### Data Flow

```
Telegram Channels → Scraper → SQLite Database → Processor → drone_data.json → Map Display
                                                                     ↓
                                                              docs/drone_data.json (GitHub Pages)
```

### Test Data Flow (Default)

```
test_data.py → drone_data.json → Map Display
                      ↓
            docs/drone_data.json
```

### Automated Service

The `auto_update_service.py` service:
1. Checks if Telegram is configured
2. If yes: Processes real Telegram data
3. If no: Generates fresh test data
4. Updates both `drone_data.json` and `docs/drone_data.json`
5. Waits 60 seconds and repeats

## Troubleshooting

### Map shows no threats

**Solution**: Run the automated service or generate test data:
```bash
python3 test_data.py
```

### Service won't start

**Check**:
- Python 3 is installed
- Required packages are installed: `pip install -r requirements.txt`

### Real Telegram data not working

**Check**:
1. Telegram credentials configured: `python3 telegram-scraper.py`
2. Channels scraped: Check for `kpszsu/kpszsu.db` and similar folders
3. Run processor manually: `python3 process_scraped_data.py`

### Map doesn't update

**Check**:
- Browser cache cleared (map auto-refreshes every 10 seconds)
- `drone_data.json` file exists and has data
- File permissions allow reading

## Advanced Usage

### Manual Data Processing

Process scraped Telegram data without the automated service:

```bash
python3 process_scraped_data.py
```

### GitHub Pages Deployment

The `docs/` folder is configured for GitHub Pages:
- `docs/index.html` - Production map
- `docs/drone_data.json` - Production data

Both files are automatically updated by the service.

### Custom Update Interval

Edit `auto_update_service.py` and change:

```python
UPDATE_INTERVAL = 60  # seconds between updates
```

## Security Notes

⚠️ **Never commit**:
- `state.json` (contains Telegram session)
- `.env` (contains API tokens)
- `*.db` files (personal Telegram data)

These are already in `.gitignore`.

## Support

For issues or questions, check:
- `README.md` - Installation and setup
- `SETUP_REAL_DATA.md` - Telegram integration guide
- `TEST.md` - Testing instructions
