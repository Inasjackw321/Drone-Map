#!/usr/bin/env python3
import os
import json
import re
import subprocess
from datetime import datetime
from telethon import TelegramClient, events

API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
CHANNEL = 'kpszsu'  # Channel username
DATA_FILE = 'drone_data.json'

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {'sightings': []}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    try:
        subprocess.run(['git', 'add', DATA_FILE], check=True)
        subprocess.run(['git', 'commit', '-m', f'Scrape: {datetime.now().isoformat()}'], check=True)
        subprocess.run(['git', 'push'], check=True)
    except:
        pass

def extract_coords(text):
    """Extract coordinates from text"""
    # Look for lat/lon patterns
    pattern = r'(\d+\.\d+)[,\s]+(\d+\.\d+)'
    match = re.search(pattern, text)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None, None

def extract_drone_info(text):
    """Extract drone type and info from message"""
    text_lower = text.lower()

    drone_types = ['shahed', 'geran', 'orlan', 'lancet', 'uav', 'drone', 'бпла', 'безпілотник']
    for dtype in drone_types:
        if dtype in text_lower:
            return dtype.capitalize()

    return 'Unknown'

async def scrape_channel():
    client = TelegramClient('drone_scraper', API_ID, API_HASH)
    await client.start()

    data = load_data()
    count = 0

    # Get last 50 messages from channel
    async for message in client.iter_messages(CHANNEL, limit=50):
        if message.text:
            lat, lon = extract_coords(message.text)

            if lat and lon:
                # Check if not already added
                exists = any(s.get('msg_id') == message.id for s in data['sightings'])

                if not exists:
                    drone_type = extract_drone_info(message.text)

                    data['sightings'].append({
                        'lat': lat,
                        'lon': lon,
                        'type': drone_type,
                        'description': message.text[:200],
                        'timestamp': message.date.isoformat(),
                        'reporter': 'telegram_scraper',
                        'msg_id': message.id
                    })
                    count += 1

    if count > 0:
        save_data(data)
        print(f'✅ Added {count} new drone sightings')
    else:
        print('No new sightings found')

    await client.disconnect()

if __name__ == '__main__':
    import asyncio
    asyncio.run(scrape_channel())
