#!/usr/bin/env python3
"""
Drone Map Web Server
Web interface for viewing drone activity maps
"""
import sys
import os
from flask import Flask, render_template, jsonify, send_file
from datetime import datetime, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.database.models import DroneSighting, SessionLocal
from src.utils.map_generator import MapGenerator
from src.config import config

app = Flask(__name__)
db = SessionLocal()
map_generator = MapGenerator()

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/map')
@app.route('/map/<int:hours>')
def view_map(hours=24):
    """Generate and display map"""
    try:
        # Generate map
        map_file = f"static/maps/current_map.html"
        os.makedirs("static/maps", exist_ok=True)

        map_generator.save_map(filename=map_file, hours=hours)

        # Return the generated map
        return send_file(map_file)
    except Exception as e:
        return f"Error generating map: {str(e)}", 500

@app.route('/api/sightings')
@app.route('/api/sightings/<int:hours>')
def api_sightings(hours=24):
    """API endpoint for getting recent sightings"""
    try:
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        sightings = db.query(DroneSighting).filter(
            DroneSighting.timestamp >= cutoff_time
        ).order_by(DroneSighting.timestamp.desc()).all()

        return jsonify({
            'count': len(sightings),
            'hours': hours,
            'sightings': [s.to_dict() for s in sightings]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def api_stats():
    """API endpoint for statistics"""
    try:
        total = db.query(DroneSighting).count()
        last_24h = db.query(DroneSighting).filter(
            DroneSighting.timestamp >= datetime.utcnow() - timedelta(hours=24)
        ).count()
        verified = db.query(DroneSighting).filter_by(verified=True).count()
        critical = db.query(DroneSighting).filter_by(threat_level='critical').count()

        return jsonify({
            'total_sightings': total,
            'last_24h': last_24h,
            'verified': verified,
            'critical_threats': critical,
            'last_updated': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.utcnow().isoformat()
    })

if __name__ == '__main__':
    print("🌐 Starting Drone Map Web Server...")
    print(f"📡 Server running on http://{config.FLASK_HOST}:{config.FLASK_PORT}")
    print(f"🗺️  View map at: http://localhost:{config.FLASK_PORT}/map")

    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=True
    )
