import sys
import os
from datetime import datetime
import random
from geopy.geocoders import Nominatim

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.models import DroneSighting, DroneTrack, SessionLocal

class DroneDataIngestion:
    def __init__(self):
        self.db = SessionLocal()
        self.geolocator = Nominatim(user_agent="drone-map")

    def add_sighting(self, latitude, longitude, altitude=None, drone_type=None,
                     direction=None, speed=None, description=None, source="manual",
                     verified=False, threat_level="low"):
        """
        Add a new drone sighting to the database
        """
        try:
            # Get region name
            region = self.get_region_name(latitude, longitude)

            sighting = DroneSighting(
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                drone_type=drone_type,
                direction=direction,
                speed=speed,
                description=description,
                source=source,
                region=region,
                verified=verified,
                threat_level=threat_level
            )

            self.db.add(sighting)
            self.db.commit()
            return sighting
        except Exception as e:
            self.db.rollback()
            print(f"Error adding sighting: {e}")
            return None

    def get_region_name(self, lat, lon):
        """
        Get region name from coordinates using reverse geocoding
        """
        try:
            location = self.geolocator.reverse(f"{lat}, {lon}", language='en')
            if location and location.raw.get('address'):
                address = location.raw['address']
                # Try to get country and state/region
                country = address.get('country', '')
                state = address.get('state', '')
                return f"{state}, {country}" if state else country
        except:
            pass
        return "Unknown"

    def get_recent_sightings(self, limit=50, region=None):
        """
        Get recent drone sightings
        """
        query = self.db.query(DroneSighting).order_by(DroneSighting.timestamp.desc())

        if region:
            query = query.filter(DroneSighting.region.contains(region))

        return query.limit(limit).all()

    def get_sightings_in_bounds(self, min_lat, max_lat, min_lon, max_lon):
        """
        Get sightings within geographic bounds
        """
        return self.db.query(DroneSighting).filter(
            DroneSighting.latitude >= min_lat,
            DroneSighting.latitude <= max_lat,
            DroneSighting.longitude >= min_lon,
            DroneSighting.longitude <= max_lon
        ).order_by(DroneSighting.timestamp.desc()).all()

    def generate_sample_data(self, count=10):
        """
        Generate sample drone sightings for testing
        Focuses on Europe and Ukraine region
        """
        drone_types = ["Quadcopter", "Shahed-136", "Orlan-10", "Bayraktar TB2", "Commercial", "Unknown"]
        threat_levels = ["low", "medium", "high", "critical"]
        directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

        # Focus on Ukraine and surrounding areas
        ukraine_regions = [
            {"name": "Kyiv", "lat": 50.4501, "lon": 30.5234},
            {"name": "Lviv", "lat": 49.8397, "lon": 24.0297},
            {"name": "Kharkiv", "lat": 49.9935, "lon": 36.2304},
            {"name": "Odesa", "lat": 46.4825, "lon": 30.7233},
            {"name": "Dnipro", "lat": 48.4647, "lon": 35.0462},
            {"name": "Warsaw", "lat": 52.2297, "lon": 21.0122},
            {"name": "Bucharest", "lat": 44.4268, "lon": 26.1025},
            {"name": "Budapest", "lat": 47.4979, "lon": 19.0402},
        ]

        for _ in range(count):
            region = random.choice(ukraine_regions)
            # Add some randomness to coordinates
            lat = region["lat"] + random.uniform(-0.5, 0.5)
            lon = region["lon"] + random.uniform(-0.5, 0.5)

            self.add_sighting(
                latitude=lat,
                longitude=lon,
                altitude=random.randint(100, 5000),
                drone_type=random.choice(drone_types),
                direction=random.choice(directions),
                speed=random.randint(20, 150),
                description=f"Drone sighting near {region['name']}",
                source="simulation",
                verified=random.choice([True, False]),
                threat_level=random.choice(threat_levels)
            )

    def close(self):
        self.db.close()
