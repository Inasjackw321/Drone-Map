#!/usr/bin/env python3
import os
import json
import sqlite3
import re
import subprocess
from datetime import datetime

DATA_FILE = 'drone_data.json'
CHANNEL_NAME = 'kpszsu'  # Default channel

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {'sightings': []}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    try:
        subprocess.run(['git', 'add', DATA_FILE], check=True, cwd='/home/user/Drone-Map')
        subprocess.run(['git', 'commit', '-m', f'Update: {datetime.now().isoformat()}'], check=True, cwd='/home/user/Drone-Map')
        subprocess.run(['git', 'push'], check=True, cwd='/home/user/Drone-Map')
    except:
        pass

def extract_coords(text):
    """Extract coordinates from various formats"""
    patterns = [
        r'(\d{2}\.\d+)[,\s]+(\d{2}\.\d+)',  # 50.123, 30.456
        r'(\d{2}\.\d+)\s+(\d{2}\.\d+)',     # 50.123 30.456
        r'координати[:\s]+(\d{2}\.\d+)[,\s]+(\d{2}\.\d+)',
        r'координаты[:\s]+(\d{2}\.\d+)[,\s]+(\d{2}\.\d+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            lat, lon = float(match.group(1)), float(match.group(2))
            if 44 <= lat <= 53 and 22 <= lon <= 41:  # Valid range for Ukraine
                return lat, lon
    return None, None

def extract_drone_type(text):
    """Extract drone type from text"""
    text_lower = text.lower()

    types = {
        'shahed': 'Shahed-136',
        'шахед': 'Shahed-136',
        'geran': 'Geran-2',
        'герань': 'Geran-2',
        'orlan': 'Orlan-10',
        'орлан': 'Orlan-10',
        'lancet': 'Lancet',
        'ланцет': 'Lancet',
        'бпла': 'UAV',
        'дрон': 'Drone',
        'безпілотник': 'UAV'
    }

    for key, value in types.items():
        if key in text_lower:
            return value

    return 'Unknown'

def process_channel_data(channel_name):
    """Process scraped data from channel database"""
    db_path = f'./{channel_name}/{channel_name}.db'

    if not os.path.exists(db_path):
        print(f"❌ No database found for channel {channel_name}")
        print(f"   Run: python telegram-scraper.py")
        return

    data = load_data()
    existing_ids = set(s.get('msg_id') for s in data['sightings'])

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get messages from last 24 hours
    cursor.execute("""
        SELECT id, text, date
        FROM messages
        WHERE text IS NOT NULL
        ORDER BY date DESC
        LIMIT 100
    """)

    new_count = 0

    for row in cursor.fetchall():
        msg_id, text, date = row

        if msg_id in existing_ids:
            continue

        lat, lon = extract_coords(text)

        if lat and lon:
            drone_type = extract_drone_type(text)

            data['sightings'].append({
                'lat': lat,
                'lon': lon,
                'type': drone_type,
                'description': text[:200],
                'timestamp': date,
                'reporter': 'telegram_scraper',
                'msg_id': msg_id,
                'channel': channel_name
            })
            new_count += 1

    conn.close()

    if new_count > 0:
        save_data(data)
        print(f'✅ Added {new_count} new drone sightings from {channel_name}')

        # Copy to docs folder for GitHub Pages
        docs_file = 'docs/drone_data.json'
        with open(docs_file, 'w') as f:
            json.dump(data, f, indent=2)

        subprocess.run(['git', 'add', docs_file], check=True)
        subprocess.run(['git', 'commit', '--amend', '--no-edit'], check=True)
        subprocess.run(['git', 'push', '-f'], check=True)
    else:
        print('No new sightings found')

if __name__ == '__main__':
    import sys
    channel = sys.argv[1] if len(sys.argv) > 1 else CHANNEL_NAME
    process_channel_data(channel)
