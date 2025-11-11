import folium
from folium.plugins import MarkerCluster, HeatMap
import sys
import os
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config
from database.models import DroneSighting, SessionLocal

class MapGenerator:
    def __init__(self):
        self.db = SessionLocal()

    def get_threat_color(self, threat_level):
        """
        Return marker color based on threat level
        """
        colors = {
            'low': 'green',
            'medium': 'orange',
            'high': 'red',
            'critical': 'darkred'
        }
        return colors.get(threat_level, 'blue')

    def create_map(self, center_lat=None, center_lon=None, zoom=6, hours=24):
        """
        Create an interactive map with drone sightings
        """
        if center_lat is None:
            center_lat = config.DEFAULT_MAP_CENTER_LAT
        if center_lon is None:
            center_lon = config.DEFAULT_MAP_CENTER_LON

        # Create base map
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=zoom,
            tiles='OpenStreetMap'
        )

        # Get recent sightings (within specified hours)
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        sightings = self.db.query(DroneSighting).filter(
            DroneSighting.timestamp >= cutoff_time
        ).all()

        if not sightings:
            return m

        # Add marker cluster for better performance
        marker_cluster = MarkerCluster().add_to(m)

        # Prepare heatmap data
        heat_data = []

        for sighting in sightings:
            # Create popup content
            popup_html = f"""
            <div style="width: 250px">
                <h4>Drone Sighting</h4>
                <b>Type:</b> {sighting.drone_type or 'Unknown'}<br>
                <b>Time:</b> {sighting.timestamp.strftime('%Y-%m-%d %H:%M:%S') if sighting.timestamp else 'Unknown'}<br>
                <b>Region:</b> {sighting.region or 'Unknown'}<br>
                <b>Altitude:</b> {sighting.altitude or 'Unknown'} m<br>
                <b>Speed:</b> {sighting.speed or 'Unknown'} km/h<br>
                <b>Direction:</b> {sighting.direction or 'Unknown'}<br>
                <b>Threat Level:</b> {sighting.threat_level or 'Unknown'}<br>
                <b>Verified:</b> {'Yes' if sighting.verified else 'No'}<br>
                <b>Source:</b> {sighting.source or 'Unknown'}<br>
                <b>Description:</b> {sighting.description or 'No description'}
            </div>
            """

            # Add marker
            folium.Marker(
                location=[sighting.latitude, sighting.longitude],
                popup=folium.Popup(popup_html, max_width=300),
                icon=folium.Icon(
                    color=self.get_threat_color(sighting.threat_level),
                    icon='plane' if sighting.drone_type else 'info-sign',
                    prefix='glyphicon'
                ),
                tooltip=f"{sighting.drone_type or 'Unknown'} - {sighting.threat_level or 'low'}"
            ).add_to(marker_cluster)

            # Add to heatmap data
            heat_data.append([sighting.latitude, sighting.longitude])

        # Add heatmap layer
        if heat_data:
            HeatMap(heat_data, radius=15, blur=25, max_zoom=13).add_to(m)

        # Add legend
        legend_html = '''
        <div style="position: fixed;
                    bottom: 50px; right: 50px; width: 200px; height: 180px;
                    background-color: white; z-index:9999; font-size:14px;
                    border:2px solid grey; border-radius: 5px; padding: 10px">
            <h4 style="margin-top:0">Threat Levels</h4>
            <p><i class="fa fa-circle" style="color:green"></i> Low</p>
            <p><i class="fa fa-circle" style="color:orange"></i> Medium</p>
            <p><i class="fa fa-circle" style="color:red"></i> High</p>
            <p><i class="fa fa-circle" style="color:darkred"></i> Critical</p>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))

        return m

    def save_map(self, filename='drone_map.html', **kwargs):
        """
        Generate and save map to file
        """
        m = self.create_map(**kwargs)
        m.save(filename)
        return filename

    def close(self):
        self.db.close()
