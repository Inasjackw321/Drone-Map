#!/usr/bin/env python3
"""
Automated Drone Tracking Service
Continuously updates drone data from Telegram channels or test data
"""
import os
import sys
import time
import json
import subprocess
from datetime import datetime
from pathlib import Path

# Configuration
UPDATE_INTERVAL = 60  # seconds between updates
USE_TEST_DATA = True  # Set to False when Telegram credentials are configured
STATE_FILE = 'state.json'

class DroneTrackingService:
    def __init__(self):
        self.running = True
        self.update_count = 0

    def log(self, message):
        """Log with timestamp"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] {message}")

    def check_telegram_configured(self):
        """Check if Telegram credentials are configured"""
        if not os.path.exists(STATE_FILE):
            return False

        try:
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                return state.get('api_id') is not None and state.get('api_hash') is not None
        except:
            return False

    def has_scraped_data(self):
        """Check if any channel databases exist"""
        channels = ['kpszsu', 'air_alert_ua', 'ukraine_now_english',
                   'nexta_live', 'uniannet', 'tchuky']

        for channel in channels:
            db_path = Path(channel) / f"{channel}.db"
            if db_path.exists():
                return True
        return False

    def run_test_data_generator(self):
        """Generate test data"""
        self.log("Generating test data...")
        try:
            result = subprocess.run(
                ['python', 'test_data.py'],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                self.log(f"✅ Test data generated: {result.stdout.strip()}")
                return True
            else:
                self.log(f"❌ Test data generation failed: {result.stderr}")
                return False
        except Exception as e:
            self.log(f"❌ Error generating test data: {e}")
            return False

    def run_processor(self):
        """Process scraped Telegram data"""
        self.log("Processing scraped Telegram data...")
        try:
            result = subprocess.run(
                ['python', 'process_scraped_data.py'],
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode == 0:
                self.log(f"✅ Data processed successfully")
                return True
            else:
                self.log(f"⚠️  Processor output: {result.stderr}")
                return False
        except Exception as e:
            self.log(f"❌ Error processing data: {e}")
            return False

    def update_data(self):
        """Main update logic"""
        self.update_count += 1
        self.log(f"=== Update #{self.update_count} ===")

        telegram_configured = self.check_telegram_configured()
        has_data = self.has_scraped_data()

        if telegram_configured and has_data:
            # Use real Telegram data
            self.log("Using real Telegram data")
            success = self.run_processor()

            if not success:
                self.log("Falling back to test data")
                self.run_test_data_generator()
        else:
            # Use test data
            if not telegram_configured:
                self.log("Telegram not configured, using test data")
            else:
                self.log("No scraped data available, using test data")

            self.run_test_data_generator()

        # Verify data file exists
        if os.path.exists('drone_data.json'):
            try:
                with open('drone_data.json', 'r') as f:
                    data = json.load(f)
                    num_sightings = len(data.get('sightings', []))
                    self.log(f"📊 Current sightings: {num_sightings}")
            except:
                pass

    def run(self):
        """Main service loop"""
        self.log("🚀 Drone Tracking Service Started")
        self.log(f"Update interval: {UPDATE_INTERVAL} seconds")

        # Initial update
        self.update_data()

        # Continuous updates
        try:
            while self.running:
                time.sleep(UPDATE_INTERVAL)
                self.update_data()
        except KeyboardInterrupt:
            self.log("\n🛑 Service stopped by user")
        except Exception as e:
            self.log(f"❌ Service error: {e}")
        finally:
            self.log("Service shutdown")

def main():
    service = DroneTrackingService()
    service.run()

if __name__ == '__main__':
    main()
