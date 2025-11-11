# Test System

## Quick Test

Generate test data with drones and missiles:

```bash
python test_data.py
```

Then commit:

```bash
git add drone_data.json docs/drone_data.json
git commit -m "Test data"
git push
```

Wait 30 seconds, then visit: https://inasjackw321.github.io/Drone-Map/

## Features Tested

- ✅ Drone tracking (yellow markers)
- ✅ Missile tracking (red markers)
- ✅ Alert zones (50km circles around cities)
- ✅ Proximity warnings (within 100km of cities)
- ✅ Real-time updates (every 10 seconds)
- ✅ Dark theme with HUD interface
- ✅ Blinking alerts for critical threats
- ✅ Animated markers with pulse effect

## Alert System

**Immediate Threat**: < 50km from city (red, blinking)
**Approaching**: 50-100km from city (yellow warning)
**Monitored**: > 100km from city (tracked, no alert)

## Cities with Alert Zones

- Kyiv
- Lviv
- Kharkiv
- Odesa
- Dnipro

Each has a 50km alert radius.

## Data Format

```json
{
  "sightings": [
    {
      "lat": 50.45,
      "lon": 30.52,
      "type": "Shahed-136",
      "category": "drone",
      "speed": 185,
      "altitude": 300,
      "direction": "NE",
      "timestamp": "2024-01-01T12:00:00",
      "threat_level": "high"
    }
  ]
}
```

**Categories**: `drone` or `missile`
**Threat Levels**: `low`, `medium`, `high`, `critical`
