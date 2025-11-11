#!/usr/bin/env python3
import os
import json
import sqlite3
import re
import subprocess
from datetime import datetime

DATA_FILE = 'drone_data.json'

CHANNELS = [
    'kpszsu',
    'air_alert_ua',
    'ukraine_now_english',
    'nexta_live',
    'uniannet',
    'tchuky'
]

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {'sightings': []}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    # Copy to docs
    with open('docs/drone_data.json', 'w') as f:
        json.dump(data, f, indent=2)

    try:
        subprocess.run(['git', 'add', DATA_FILE, 'docs/drone_data.json'], check=True)
        subprocess.run(['git', 'commit', '-m', f'Update: {datetime.now().isoformat()}'], check=True)
        subprocess.run(['git', 'push'], check=True)
    except Exception as e:
        print(f"Git error: {e}")

def extract_coords(text):
    """Extract coordinates from various formats"""
    patterns = [
        r'(\d{2}\.\d+)[,\s]+(\d{2}\.\d+)',
        r'(\d{2}\.\d+)\s+(\d{2}\.\d+)',
        r'координати[:\s]+(\d{2}\.\d+)[,\s]+(\d{2}\.\d+)',
        r'координаты[:\s]+(\d{2}\.\d+)[,\s]+(\d{2}\.\d+)',
        r'coords?[:\s]+(\d{2}\.\d+)[,\s]+(\d{2}\.\d+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            lat, lon = float(match.group(1)), float(match.group(2))
            if 44 <= lat <= 53 and 22 <= lon <= 41:
                return lat, lon
    return None, None

def extract_threat_info(text):
    """Extract threat type, category, and details from text"""
    text_lower = text.lower()

    # Drone types
    drone_types = {
        'shahed': ('Shahed-136', 'drone', 185, 300, 'medium'),
        'шахед': ('Shahed-136', 'drone', 185, 300, 'medium'),
        'geran': ('Geran-2', 'drone', 185, 300, 'medium'),
        'герань': ('Geran-2', 'drone', 185, 300, 'medium'),
        'orlan': ('Orlan-10', 'drone', 150, 5000, 'medium'),
        'орлан': ('Orlan-10', 'drone', 150, 5000, 'medium'),
        'lancet': ('Lancet', 'drone', 110, 500, 'medium'),
        'ланцет': ('Lancet', 'drone', 110, 500, 'medium'),
    }

    # Missile types
    missile_types = {
        'kalibr': ('Kalibr Missile', 'missile', 900, 10000, 'high'),
        'калібр': ('Kalibr Missile', 'missile', 900, 10000, 'high'),
        'iskander': ('Iskander Missile', 'missile', 2100, 50000, 'high'),
        'іскандер': ('Iskander Missile', 'missile', 2100, 50000, 'high'),
        'kh-101': ('Kh-101 Missile', 'missile', 1000, 6000, 'high'),
        'х-101': ('Kh-101 Missile', 'missile', 1000, 6000, 'high'),
        'kh-47': ('Kh-47 Kinzhal', 'missile', 4900, 20000, 'high'),
        'х-47': ('Kh-47 Kinzhal', 'missile', 4900, 20000, 'high'),
        'kinzhal': ('Kh-47 Kinzhal', 'missile', 4900, 20000, 'high'),
        'кинжал': ('Kh-47 Kinzhal', 'missile', 4900, 20000, 'high'),
        'rocket': ('Missile', 'missile', 900, 10000, 'high'),
        'ракета': ('Missile', 'missile', 900, 10000, 'high'),
    }

    all_types = {**drone_types, **missile_types}

    for key, (name, category, speed, altitude, threat) in all_types.items():
        if key in text_lower:
            return name, category, speed, altitude, threat

    # Default to drone if generic UAV terms found
    if any(term in text_lower for term in ['бпла', 'uav', 'дрон', 'drone', 'безпілотник', 'бп']):
        return 'UAV', 'drone', 150, 1000, 'medium'

    return None, None, None, None, None

def process_channel_data(channel_name):
    """Process scraped data from channel database"""
    db_path = f'./{channel_name}/{channel_name}.db'

    if not os.path.exists(db_path):
        print(f"⏭️  Skipping {channel_name} - no database")
        return 0

    data = load_data()
    existing_ids = set(f"{s.get('channel')}_{s.get('msg_id')}" for s in data['sightings'])

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, text, date
        FROM messages
        WHERE text IS NOT NULL
        ORDER BY date DESC
        LIMIT 200
    """)

    new_count = 0

    for row in cursor.fetchall():
        msg_id, text, date = row
        unique_id = f"{channel_name}_{msg_id}"

        if unique_id in existing_ids:
            continue

        lat, lon = extract_coords(text)

        if lat and lon:
            threat_name, category, speed, altitude, threat_level = extract_threat_info(text)

            # Skip if we can't identify the threat type
            if not threat_name:
                continue

            # Extract direction if present
            directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
            direction = 'Unknown'
            for d in directions:
                if d.lower() in text.lower():
                    direction = d
                    break

            data['sightings'].append({
                'id': len(data['sightings']) + 1,
                'lat': lat,
                'lon': lon,
                'type': threat_name,
                'category': category,
                'speed': speed,
                'altitude': altitude,
                'direction': direction,
                'timestamp': date,
                'description': text[:200],
                'reporter': 'telegram_scraper',
                'active': True,
                'threat_level': threat_level,
                'msg_id': msg_id,
                'channel': channel_name
            })
            new_count += 1

    conn.close()
    return new_count

def process_all_channels():
    """Process all channels"""
    print("🔄 Processing channels...")
    total = 0

    for channel in CHANNELS:
        count = process_channel_data(channel)
        if count > 0:
            print(f"  ✅ {channel}: {count} new sightings")
            total += count

    if total > 0:
        data = load_data()
        save_data(data)
        print(f"\n✅ Total: {total} new drone sightings")
        print(f"📍 Total sightings in database: {len(data['sightings'])}")
    else:
        print("No new sightings found")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        count = process_channel_data(sys.argv[1])
        if count > 0:
            data = load_data()
            save_data(data)
            print(f"✅ Added {count} new sightings")
    else:
        process_all_channels()
