#!/bin/bash
# Start Drone Tracking Service
# This service automatically updates drone and missile tracking data

echo "🚀 Starting Drone Tracking Service..."
echo ""
echo "The service will:"
echo "  - Check for Telegram data every 60 seconds"
echo "  - Process new sightings automatically"
echo "  - Update the map in real-time"
echo ""
echo "Press Ctrl+C to stop"
echo ""

cd /home/user/Drone-Map
python3 auto_update_service.py
