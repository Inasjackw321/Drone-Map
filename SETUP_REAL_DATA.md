# Setup Real Telegram Data

## Prerequisites

You need Telegram API credentials:

1. Go to https://my.telegram.org/apps
2. Log in with your phone number
3. Create a new app
4. Copy your `API_ID` and `API_HASH`

## Step 1: Install Dependencies

```bash
pip install -r scraper-requirements.txt
```

## Step 2: Run the Scraper

```bash
python telegram-scraper.py
```

Follow the prompts:
- Enter your `API_ID`
- Enter your `API_HASH`
- Choose QR code login (option 2)
- Scan the QR code with Telegram app

## Step 3: Add Channels

When prompted, add these channels one by one:
- `kpszsu`
- `air_alert_ua`
- `ukraine_now_english`
- `nexta_live`
- `uniannet`
- `tchuky`

After adding all channels, press `[S]` to scrape all.

## Step 4: Process the Data

```bash
python process_scraped_data.py
```

This will:
- Extract coordinates and threat types from all channels
- Identify drones vs missiles
- Update `drone_data.json` with real data
- Automatically commit and push to GitHub

## Step 5: Auto-Update (Optional)

Set up automatic updates every 5 minutes:

```bash
while true; do
    echo "$(date) - Scraping channels..."
    python telegram-scraper.py --auto
    python process_scraped_data.py
    sleep 300
done
```

## Data Format

The processor extracts:
- **Coordinates**: Lat/lon in various formats
- **Threat Types**:
  - Drones: Shahed-136, Geran-2, Orlan-10, Lancet
  - Missiles: Kalibr, Iskander, Kh-101, Kinzhal
- **Details**: Speed, altitude, direction, threat level
- **Language Support**: Ukrainian and English

## Verification

After processing, check your map at:
https://inasjackw321.github.io/Drone-Map/

It should show real-time threats from Telegram channels instead of test data.
