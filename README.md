# Drone Tracker

Live map showing drone locations from multiple Telegram channels.

## Live Map

https://inasjackw321.github.io/Drone-Map/

## Channels Monitored

- @kpszsu
- @air_alert_ua
- @ukraine_now_english
- @nexta_live
- @uniannet
- @tchuky

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
- Choose QR code login
- Add all channels (paste each one):
  - `kpszsu`
  - `air_alert_ua`
  - `ukraine_now_english`
  - `nexta_live`
  - `uniannet`
  - `tchuky`
- Press [S] to scrape all

### 4. Process Data

```bash
python process_scraped_data.py
```

Processes all channels and extracts drone coordinates.

### 5. Auto-run

```bash
while true; do
    python telegram-scraper.py
    python process_scraped_data.py
    sleep 300
done
```

## How It Works

1. Scraper downloads messages from all channels
2. Processor extracts coordinates from messages
3. Updates drone_data.json with new sightings
4. Auto-commits to GitHub
5. GitHub Pages map updates automatically

## Adding More Channels

Edit `process_scraped_data.py` and add to CHANNELS list:

```python
CHANNELS = [
    'kpszsu',
    'your_channel_here'
]
```
