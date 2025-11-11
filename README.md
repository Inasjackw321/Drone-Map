# 🛰️ Drone Map - Europe & Ukraine Tracker

A real-time drone tracking system with Telegram bot integration for monitoring drone activity in Europe and Ukraine.

## Features

- 🤖 **Telegram Bot** - Interactive bot for tracking drones
- 🗺️ **Interactive Maps** - Visualize drone activity with heatmaps
- 🔔 **Real-time Alerts** - Subscribe to notifications for new sightings
- 📊 **Statistics** - View comprehensive tracking statistics
- 📝 **User Reports** - Allow users to report drone sightings
- 🎯 **Threat Levels** - Color-coded threat assessment (low, medium, high, critical)
- 🌍 **Geographic Focus** - Specialized tracking for Europe and Ukraine regions

## Architecture

```
Drone-Map/
├── src/
│   ├── bot/              # Telegram bot implementation
│   ├── database/         # Database models and schema
│   ├── utils/            # Utilities (data ingestion, maps)
│   └── config.py         # Configuration management
├── static/               # Static files (generated maps)
├── templates/            # HTML templates
├── main.py               # Main application entry point
├── requirements.txt      # Python dependencies
└── .env                  # Environment variables (create from .env.example)
```

## Prerequisites

- Python 3.8 or higher
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- pip (Python package manager)

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/Drone-Map.git
cd Drone-Map
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and add your Telegram Bot Token:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

### 5. Initialize the database

```bash
python main.py --init-db
```

### 6. (Optional) Generate sample data for testing

```bash
python main.py --generate-data 50
```

## Usage

### Start the Telegram Bot

```bash
python main.py --start-bot
```

### Telegram Bot Commands

Once the bot is running, you can interact with it on Telegram:

- `/start` - Welcome message and introduction
- `/help` - Show all available commands
- `/track [hours]` - Get recent drone sightings (default: 24 hours)
- `/map [hours]` - Generate interactive map (default: 24 hours)
- `/stats` - View current statistics
- `/subscribe` - Subscribe to real-time alerts
- `/unsubscribe` - Unsubscribe from alerts
- `/report <lat> <lon> <type> <description>` - Report a drone sighting

### Example Commands

```
/track 12               # Show sightings from last 12 hours
/map 6                  # Generate map for last 6 hours
/report 50.45 30.52 Quadcopter Spotted near Kyiv
```

## Creating a Telegram Bot

1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot` command
3. Follow the instructions to choose a name and username
4. Copy the bot token provided by BotFather
5. Add the token to your `.env` file

## Database Schema

### DroneSighting
- Timestamp, location (lat/lon), altitude
- Drone type, direction, speed
- Description, source, region
- Verification status, threat level

### TelegramSubscriber
- Chat ID, username
- Subscription status, notification preferences

### DroneTrack
- Track ID, first/last seen timestamps
- Start and current positions
- Active status, drone type

## Data Sources

Currently, the system supports:
- Manual user reports via Telegram bot
- Sample data generation for testing
- API integration ready for real-time data feeds

To integrate with real drone tracking APIs, modify `src/utils/data_ingestion.py`

## Map Visualization

Maps are generated using Folium and include:
- **Markers** - Individual drone sightings with color-coded threat levels
- **Heatmap** - Density visualization of drone activity
- **Popups** - Detailed information for each sighting
- **Legend** - Threat level color coding

### Threat Level Colors
- 🟢 Green - Low threat
- 🟡 Orange - Medium threat
- 🔴 Red - High threat
- 🔴🔴 Dark Red - Critical threat

## Security Considerations

- Keep your `.env` file secure and never commit it to version control
- The `.gitignore` file is configured to exclude sensitive files
- Bot token should be kept private
- Consider implementing rate limiting for user reports
- Implement verification system for crowdsourced data

## Development

### Project Structure

```python
# Main application
main.py                   # Entry point

# Bot module
src/bot/telegram_bot.py   # Telegram bot implementation

# Database module
src/database/models.py    # SQLAlchemy models

# Utils module
src/utils/data_ingestion.py  # Data collection and processing
src/utils/map_generator.py   # Map visualization

# Configuration
src/config.py             # Config management
.env                      # Environment variables
```

### Adding New Features

1. **New Commands**: Add handlers in `src/bot/telegram_bot.py`
2. **Database Models**: Extend models in `src/database/models.py`
3. **Data Sources**: Add integrations in `src/utils/data_ingestion.py`
4. **Visualization**: Enhance maps in `src/utils/map_generator.py`

## Troubleshooting

### Bot not responding
- Check that `TELEGRAM_BOT_TOKEN` is correctly set in `.env`
- Verify bot is running with `--start-bot` flag
- Check console for error messages

### Database errors
- Run `python main.py --init-db` to recreate database
- Check file permissions for `drone_map.db`

### Map generation fails
- Ensure `static/maps/` directory exists
- Check disk space
- Verify database has sighting data

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is open source and available under the MIT License.

## Disclaimer

This is a tracking and monitoring tool for educational and informational purposes. Always verify information from official sources. The accuracy of crowdsourced data depends on user reports and should be verified independently.

## Support

For issues, questions, or suggestions:
- Open an issue on GitHub
- Contact via Telegram

---

**Stay Informed. Stay Safe.** 🛡️
