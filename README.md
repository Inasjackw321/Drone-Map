# Drone Tracker

Live map showing drone locations scraped from Telegram.

## Live Map

https://inasjackw321.github.io/Drone-Map/

## Auto-Scrape from Telegram

Scrapes drone data from https://t.me/kpszsu

### Setup

1. Get Telegram API credentials:
   - Go to https://my.telegram.org/apps
   - Create app, get API_ID and API_HASH

2. Set environment variables:
```bash
export TELEGRAM_API_ID=your_api_id
export TELEGRAM_API_HASH=your_api_hash
```

3. Run scraper:
```bash
pip install -r requirements.txt
python scraper.py
```

Scraper extracts coordinates and drone info, auto-commits to GitHub.

### Run continuously:
```bash
while true; do python scraper.py; sleep 300; done
```

## Manual Reporting (Optional)

Set up bot for manual reports:
```bash
export TELEGRAM_BOT_TOKEN=your_token
python telegram_bot.py
```

Report: `/report 50.45 30.52 Drone`
