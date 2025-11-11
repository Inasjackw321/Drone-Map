import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

    # Database Configuration
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///drone_map.db')

    # Web Server Configuration
    FLASK_PORT = int(os.getenv('FLASK_PORT', 5000))
    FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')

    # Map Configuration
    DEFAULT_MAP_CENTER_LAT = float(os.getenv('DEFAULT_MAP_CENTER_LAT', 50.4501))
    DEFAULT_MAP_CENTER_LON = float(os.getenv('DEFAULT_MAP_CENTER_LON', 30.5234))
    DEFAULT_MAP_ZOOM = int(os.getenv('DEFAULT_MAP_ZOOM', 6))

    # Update Interval (in seconds)
    DATA_UPDATE_INTERVAL = int(os.getenv('DATA_UPDATE_INTERVAL', 300))

    # Europe and Ukraine boundaries for filtering
    EUROPE_UKRAINE_BOUNDS = {
        'min_lat': 44.0,
        'max_lat': 52.0,
        'min_lon': 22.0,
        'max_lon': 40.0
    }

config = Config()
