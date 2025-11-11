# Drone Tracker

Live map showing drone locations from Telegram channel @kpszsu.

## Live Map

https://inasjackw321.github.io/Drone-Map/

## Setup

### 1. Get Telegram API Credentials

1. Go to https://my.telegram.org/apps
2. Create app
3. Get API_ID and API_HASH

### 2. Install Dependencies

```bash
pip install -r scraper-requirements.txt
```

### 3. Run Scraper

```bash
python telegram-scraper.py
```

Follow prompts:
- Enter API_ID and API_HASH
- Choose QR code login (recommended)
- Add channel: `kpszsu`
- Select option [S] to scrape

### 4. Process Data

```bash
python process_scraped_data.py kpszsu
```

This extracts coordinates from messages and updates the map.

### 5. Auto-run (Optional)

```bash
while true; do
    python telegram-scraper.py
    python process_scraped_data.py kpszsu
    sleep 300
done
```

## Files

- `telegram-scraper.py` - Main scraper (from unnohwn/telegram-scraper)
- `process_scraped_data.py` - Extracts drone coordinates from scraped messages
- `drone_data.json` - Drone locations data
- `docs/` - GitHub Pages site

## How It Works

1. Scraper downloads messages from @kpszsu channel
2. Processor extracts coordinates from messages
3. Updates drone_data.json
4. Auto-commits to GitHub
5. GitHub Pages displays updated map
