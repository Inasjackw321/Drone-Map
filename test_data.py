#!/usr/bin/env python3
import json
import random
from datetime import datetime, timedelta

DATA_FILE = 'drone_data.json'

REGIONS = {
    'Kyiv': {'lat': 50.4501, 'lon': 30.5234},
    'Lviv': {'lat': 49.8397, 'lon': 24.0297},
    'Kharkiv': {'lat': 49.9935, 'lon': 36.2304},
    'Odesa': {'lat': 46.4825, 'lon': 30.7233},
    'Dnipro': {'lat': 48.4647, 'lon': 35.0462},
    'Zaporizhzhia': {'lat': 47.8388, 'lon': 35.1396},
    'Vinnytsia': {'lat': 49.2328, 'lon': 28.4681},
}

THREAT_TYPES = [
    {'type': 'Shahed-136', 'speed': 185, 'altitude': 300, 'category': 'drone'},
    {'type': 'Geran-2', 'speed': 185, 'altitude': 300, 'category': 'drone'},
    {'type': 'Orlan-10', 'speed': 150, 'altitude': 5000, 'category': 'drone'},
    {'type': 'Kalibr Missile', 'speed': 900, 'altitude': 10000, 'category': 'missile'},
    {'type': 'Iskander Missile', 'speed': 2100, 'altitude': 50000, 'category': 'missile'},
    {'type': 'Kh-101 Missile', 'speed': 1000, 'altitude': 6000, 'category': 'missile'},
]

DIRECTIONS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']

def generate_test_data():
    """Generate realistic test data"""
    data = {'sightings': [], 'alerts': []}

    # Generate 15-25 threats
    num_threats = random.randint(15, 25)

    for i in range(num_threats):
        region = random.choice(list(REGIONS.values()))
        threat = random.choice(THREAT_TYPES)

        # Random offset from region center (within 50km)
        lat_offset = random.uniform(-0.5, 0.5)
        lon_offset = random.uniform(-0.5, 0.5)

        # Random time in last 30 minutes
        minutes_ago = random.randint(0, 30)
        timestamp = datetime.utcnow() - timedelta(minutes=minutes_ago)

        direction = random.choice(DIRECTIONS)

        sighting = {
            'id': i + 1,
            'lat': region['lat'] + lat_offset,
            'lon': region['lon'] + lon_offset,
            'type': threat['type'],
            'category': threat['category'],
            'speed': threat['speed'] + random.randint(-50, 50),
            'altitude': threat['altitude'] + random.randint(-500, 500),
            'direction': direction,
            'timestamp': timestamp.isoformat(),
            'description': f"{threat['type']} heading {direction}",
            'reporter': 'test_system',
            'active': True,
            'threat_level': 'high' if threat['category'] == 'missile' else 'medium'
        }

        data['sightings'].append(sighting)

    # Save to files
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    with open('docs/drone_data.json', 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✅ Generated {num_threats} test threats")
    print(f"   - {len([s for s in data['sightings'] if s['category'] == 'drone'])} drones")
    print(f"   - {len([s for s in data['sightings'] if s['category'] == 'missile'])} missiles")

if __name__ == '__main__':
    generate_test_data()
