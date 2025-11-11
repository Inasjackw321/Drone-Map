from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

Base = declarative_base()

class DroneSighting(Base):
    __tablename__ = 'drone_sightings'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    altitude = Column(Float)
    drone_type = Column(String(100))
    direction = Column(String(50))
    speed = Column(Float)
    description = Column(Text)
    source = Column(String(100))
    region = Column(String(100))
    verified = Column(Boolean, default=False)
    threat_level = Column(String(20))  # low, medium, high, critical

    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'altitude': self.altitude,
            'drone_type': self.drone_type,
            'direction': self.direction,
            'speed': self.speed,
            'description': self.description,
            'source': self.source,
            'region': self.region,
            'verified': self.verified,
            'threat_level': self.threat_level
        }

class TelegramSubscriber(Base):
    __tablename__ = 'telegram_subscribers'

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(100))
    subscribed_at = Column(DateTime, default=datetime.utcnow)
    active = Column(Boolean, default=True)
    notify_regions = Column(String(500))  # Comma-separated list of regions

class DroneTrack(Base):
    __tablename__ = 'drone_tracks'

    id = Column(Integer, primary_key=True)
    track_id = Column(String(100), unique=True, nullable=False)
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    start_lat = Column(Float)
    start_lon = Column(Float)
    current_lat = Column(Float)
    current_lon = Column(Float)
    active = Column(Boolean, default=True)
    drone_type = Column(String(100))

# Database setup
engine = create_engine(config.DATABASE_URL)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        return db
    finally:
        pass

def init_db():
    Base.metadata.create_all(engine)
