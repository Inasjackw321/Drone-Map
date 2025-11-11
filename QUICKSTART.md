# 🚀 Quick Start Guide

Get Drone Map up and running in 5 minutes!

## Prerequisites

- Python 3.8+
- Telegram account
- 5 minutes of your time

## Step 1: Get a Telegram Bot Token

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` and follow the instructions
3. Copy the bot token (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

## Step 2: Quick Setup

### Option A: Automated Setup (Linux/Mac)

```bash
chmod +x setup.sh
./setup.sh
```

### Option B: Manual Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Create environment file
cp .env.example .env

# Edit .env and add your bot token
nano .env  # or use your favorite editor

# Initialize database
python main.py --init-db

# Generate sample data (optional)
python main.py --generate-data 20
```

## Step 3: Start the Bot

```bash
python main.py --start-bot
```

That's it! Your bot is now running!

## Step 4: Test on Telegram

1. Open Telegram
2. Search for your bot (the username you chose)
3. Send `/start`
4. Try `/track` to see recent sightings
5. Try `/map` to generate an interactive map

## Optional: Web Interface

In a separate terminal:

```bash
python web_server.py
```

Then visit: http://localhost:5000

## Docker Deployment

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f
```

## Need Help?

Check out the full [README.md](README.md) for detailed documentation.

## Common Issues

### Bot token error
- Make sure you copied the entire token from BotFather
- Check that `.env` file exists and has `TELEGRAM_BOT_TOKEN=your_token`

### No data showing
- Run `python main.py --generate-data 50` to create sample data

### Import errors
- Make sure you're in the virtual environment
- Run `pip install -r requirements.txt` again

---

**Have fun tracking drones!** 🛰️
