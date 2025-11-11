#!/usr/bin/env python3
"""
Drone Map - Europe & Ukraine Tracker
Main application entry point
"""
import sys
import os
import argparse
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.bot.telegram_bot import DroneTelegramBot
from src.database.models import init_db
from src.utils.data_ingestion import DroneDataIngestion
from src.config import config

def init_database():
    """Initialize the database"""
    print("📦 Initializing database...")
    init_db()
    print("✅ Database initialized successfully")

def generate_sample_data(count=10):
    """Generate sample drone sightings for testing"""
    print(f"🔄 Generating {count} sample drone sightings...")
    ingestion = DroneDataIngestion()
    ingestion.generate_sample_data(count)
    ingestion.close()
    print("✅ Sample data generated successfully")

def start_bot():
    """Start the Telegram bot"""
    if not config.TELEGRAM_BOT_TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN not set!")
        print("📝 Please create a .env file with your Telegram bot token")
        print("   Copy .env.example to .env and add your token")
        return

    print("🚀 Starting Drone Map Telegram Bot...")
    bot = DroneTelegramBot()
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n👋 Shutting down bot...")
        bot.close()
    except Exception as e:
        print(f"❌ Error: {e}")
        bot.close()

def main():
    parser = argparse.ArgumentParser(
        description='Drone Map - Track drones in Europe and Ukraine'
    )
    parser.add_argument(
        '--init-db',
        action='store_true',
        help='Initialize the database'
    )
    parser.add_argument(
        '--generate-data',
        type=int,
        metavar='N',
        help='Generate N sample drone sightings'
    )
    parser.add_argument(
        '--start-bot',
        action='store_true',
        help='Start the Telegram bot'
    )

    args = parser.parse_args()

    # Print banner
    print("=" * 60)
    print("🛰️  DRONE MAP - Europe & Ukraine Tracker")
    print("=" * 60)
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    # If no arguments, show help
    if len(sys.argv) == 1:
        parser.print_help()
        print("\n💡 Quick start:")
        print("   1. python main.py --init-db")
        print("   2. python main.py --generate-data 20")
        print("   3. python main.py --start-bot")
        return

    # Execute commands
    if args.init_db:
        init_database()

    if args.generate_data:
        generate_sample_data(args.generate_data)

    if args.start_bot:
        start_bot()

if __name__ == '__main__':
    main()
