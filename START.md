# Quick Start

## 1. Create Telegram Bot

1. Open Telegram, search for @BotFather
2. Send `/newbot`
3. Follow prompts to create bot
4. Copy the bot token

## 2. Run Bot

```bash
export TELEGRAM_BOT_TOKEN=your_token_here
python telegram_bot.py
```

## 3. Report Drones

In your Telegram bot, send:

```
/report 50.45 30.52 Quadcopter Spotted flying east
```

## 4. View Live Map

Visit: https://inasjackw321.github.io/Drone-Map/

Map updates automatically every minute.

## Commands

- `/start` - Show help
- `/report <lat> <lon> <type> <desc>` - Report drone sighting
- `/list` - View recent sightings

## Example Reports

```
/report 50.4501 30.5234 Shahed-136 Heading northwest
/report 49.8397 24.0297 Quadcopter Hovering near building
/report 49.9935 36.2304 Unknown Fast moving object
```
