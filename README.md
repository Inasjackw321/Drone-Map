# 🛰️ Drone Tracker

Live drone tracking system. Report via Telegram, view on map.

## Live Site

**https://inasjackw321.github.io/Drone-Map/**

## Setup Telegram Bot

1. Create bot with @BotFather on Telegram
2. Get bot token
3. Set environment variable:
```bash
export TELEGRAM_BOT_TOKEN=your_token_here
```

4. Run bot:
```bash
pip install python-telegram-bot
python telegram_bot.py
```

## Report Drones

In Telegram, send:
```
/report 50.45 30.52 Quadcopter Spotted near city
```

Format: `/report <latitude> <longitude> <type> <description>`

## How It Works

1. Users report drones via Telegram bot
2. Bot saves to `drone_data.json`
3. Bot commits and pushes to GitHub
4. Website auto-updates from GitHub
