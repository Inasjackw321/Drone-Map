// Drone Map Application
class DroneMap {
    constructor() {
        this.map = null;
        this.markers = [];
        this.heatLayer = null;
        this.currentTimeFilter = 24;
        this.apiEndpoint = this.getApiEndpoint();
        this.init();
    }

    getApiEndpoint() {
        // If running locally with backend, use localhost
        // If on GitHub Pages, use mock data
        const hostname = window.location.hostname;
        if (hostname === 'localhost' || hostname === '127.0.0.1') {
            return 'http://localhost:5000/api';
        }
        // GitHub Pages - use mock data
        return null;
    }

    async init() {
        this.initMap();
        this.attachEventListeners();
        await this.loadData();
        // Refresh data every 5 minutes
        setInterval(() => this.loadData(), 300000);
    }

    initMap() {
        // Initialize Leaflet map centered on Ukraine
        this.map = L.map('map').setView([50.4501, 30.5234], 6);

        // Add OpenStreetMap tiles
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 18
        }).addTo(this.map);

        // Add fullscreen handler
        document.getElementById('viewFullscreen').addEventListener('click', () => {
            const mapContainer = document.querySelector('.map-section');
            if (mapContainer.requestFullscreen) {
                mapContainer.requestFullscreen();
            }
        });
    }

    attachEventListeners() {
        document.getElementById('refreshBtn').addEventListener('click', () => {
            this.loadData();
        });

        document.getElementById('timeFilter').addEventListener('change', (e) => {
            this.currentTimeFilter = parseInt(e.target.value);
            this.loadData();
        });
    }

    async loadData() {
        this.showLoading(true);

        try {
            let data;
            if (this.apiEndpoint) {
                // Try to fetch from backend API
                data = await this.fetchFromApi();
            } else {
                // Use mock data for GitHub Pages demo
                data = this.getMockData();
            }

            this.updateStats(data.stats);
            this.updateMap(data.sightings);
            this.updateSightingsList(data.sightings);
            this.updateLastUpdate();
        } catch (error) {
            console.error('Error loading data:', error);
            // Fallback to mock data
            const data = this.getMockData();
            this.updateStats(data.stats);
            this.updateMap(data.sightings);
            this.updateSightingsList(data.sightings);
            this.updateLastUpdate();
        }

        this.showLoading(false);
    }

    async fetchFromApi() {
        const [statsRes, sightingsRes] = await Promise.all([
            fetch(`${this.apiEndpoint}/stats`),
            fetch(`${this.apiEndpoint}/sightings/${this.currentTimeFilter}`)
        ]);

        const stats = await statsRes.json();
        const sightingsData = await sightingsRes.json();

        return {
            stats: stats,
            sightings: sightingsData.sightings
        };
    }

    getMockData() {
        // Generate mock data for demonstration
        const droneTypes = ['Quadcopter', 'Shahed-136', 'Orlan-10', 'Bayraktar TB2', 'Commercial', 'Unknown'];
        const threatLevels = ['low', 'medium', 'high', 'critical'];
        const directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];

        const locations = [
            { name: 'Kyiv', lat: 50.4501, lon: 30.5234 },
            { name: 'Lviv', lat: 49.8397, lon: 24.0297 },
            { name: 'Kharkiv', lat: 49.9935, lon: 36.2304 },
            { name: 'Odesa', lat: 46.4825, lon: 30.7233 },
            { name: 'Dnipro', lat: 48.4647, lon: 35.0462 },
            { name: 'Warsaw', lat: 52.2297, lon: 21.0122 },
            { name: 'Bucharest', lat: 44.4268, lon: 26.1025 },
            { name: 'Budapest', lat: 47.4979, lon: 19.0402 }
        ];

        const sightings = [];
        const count = Math.floor(Math.random() * 20) + 30; // 30-50 sightings

        for (let i = 0; i < count; i++) {
            const location = locations[Math.floor(Math.random() * locations.length)];
            const hoursAgo = Math.random() * this.currentTimeFilter;
            const timestamp = new Date(Date.now() - hoursAgo * 3600000);

            sightings.push({
                id: i + 1,
                latitude: location.lat + (Math.random() - 0.5),
                longitude: location.lon + (Math.random() - 0.5),
                altitude: Math.floor(Math.random() * 5000) + 100,
                drone_type: droneTypes[Math.floor(Math.random() * droneTypes.length)],
                direction: directions[Math.floor(Math.random() * directions.length)],
                speed: Math.floor(Math.random() * 130) + 20,
                description: `Drone sighting near ${location.name}`,
                source: 'simulation',
                region: `${location.name}, Ukraine`,
                verified: Math.random() > 0.5,
                threat_level: threatLevels[Math.floor(Math.random() * threatLevels.length)],
                timestamp: timestamp.toISOString()
            });
        }

        // Sort by timestamp (newest first)
        sightings.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

        const stats = {
            total_sightings: Math.floor(Math.random() * 500) + 200,
            last_24h: sightings.filter(s => {
                const hoursDiff = (Date.now() - new Date(s.timestamp)) / 3600000;
                return hoursDiff <= 24;
            }).length,
            verified: sightings.filter(s => s.verified).length,
            critical_threats: sightings.filter(s => s.threat_level === 'critical').length
        };

        return { stats, sightings };
    }

    updateStats(stats) {
        document.getElementById('totalSightings').textContent = stats.total_sightings || '-';
        document.getElementById('recentSightings').textContent = stats.last_24h || '-';
        document.getElementById('verifiedSightings').textContent = stats.verified || '-';
        document.getElementById('criticalThreats').textContent = stats.critical_threats || '-';
    }

    updateMap(sightings) {
        // Clear existing markers
        this.markers.forEach(marker => this.map.removeLayer(marker));
        this.markers = [];

        if (this.heatLayer) {
            this.map.removeLayer(this.heatLayer);
        }

        if (!sightings || sightings.length === 0) {
            return;
        }

        // Prepare data for heatmap
        const heatData = [];

        // Add markers for each sighting
        sightings.forEach(sighting => {
            const color = this.getThreatColor(sighting.threat_level);
            const icon = L.divIcon({
                className: 'custom-marker',
                html: `<div style="background-color: ${color}; width: 20px; height: 20px; border-radius: 50%; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3);"></div>`,
                iconSize: [20, 20]
            });

            const marker = L.marker([sighting.latitude, sighting.longitude], { icon })
                .addTo(this.map);

            // Create popup
            const popupContent = `
                <div style="min-width: 200px;">
                    <h4 style="margin-bottom: 8px; color: #667eea;">${sighting.drone_type || 'Unknown'}</h4>
                    <p style="margin: 4px 0;"><strong>Time:</strong> ${this.formatTimestamp(sighting.timestamp)}</p>
                    <p style="margin: 4px 0;"><strong>Region:</strong> ${sighting.region || 'Unknown'}</p>
                    <p style="margin: 4px 0;"><strong>Altitude:</strong> ${sighting.altitude || '?'}m</p>
                    <p style="margin: 4px 0;"><strong>Speed:</strong> ${sighting.speed || '?'} km/h</p>
                    <p style="margin: 4px 0;"><strong>Direction:</strong> ${sighting.direction || '?'}</p>
                    <p style="margin: 4px 0;"><strong>Threat Level:</strong> <span style="color: ${color}; font-weight: bold;">${sighting.threat_level || 'Unknown'}</span></p>
                    ${sighting.verified ? '<p style="margin: 4px 0;">✅ Verified</p>' : ''}
                </div>
            `;

            marker.bindPopup(popupContent);
            this.markers.push(marker);

            // Add to heatmap data
            heatData.push([sighting.latitude, sighting.longitude, 0.5]);
        });

        // Add heatmap layer
        if (heatData.length > 0) {
            this.heatLayer = L.heatLayer(heatData, {
                radius: 25,
                blur: 35,
                maxZoom: 10,
                gradient: {
                    0.0: '#10b981',
                    0.5: '#f59e0b',
                    0.7: '#ef4444',
                    1.0: '#dc2626'
                }
            }).addTo(this.map);
        }

        // Fit map bounds to markers
        if (this.markers.length > 0) {
            const group = L.featureGroup(this.markers);
            this.map.fitBounds(group.getBounds().pad(0.1));
        }
    }

    updateSightingsList(sightings) {
        const listContainer = document.getElementById('sightingsList');

        if (!sightings || sightings.length === 0) {
            listContainer.innerHTML = '<div class="loading">No sightings in the selected time period.</div>';
            return;
        }

        // Show only the 10 most recent
        const recentSightings = sightings.slice(0, 10);

        listContainer.innerHTML = recentSightings.map(sighting => `
            <div class="sighting-item threat-${sighting.threat_level}">
                <div class="sighting-icon">${this.getThreatEmoji(sighting.threat_level)}</div>
                <div class="sighting-details">
                    <h4>${sighting.drone_type || 'Unknown Drone'}</h4>
                    <div class="sighting-meta">
                        <span>📍 ${sighting.region || 'Unknown'}</span>
                        <span>⬆️ ${sighting.altitude || '?'}m</span>
                        <span>🧭 ${sighting.direction || '?'}</span>
                        <span>💨 ${sighting.speed || '?'} km/h</span>
                        ${sighting.verified ? '<span>✅ Verified</span>' : ''}
                    </div>
                </div>
                <div class="sighting-time">
                    ${this.getTimeAgo(sighting.timestamp)}
                </div>
            </div>
        `).join('');
    }

    getThreatColor(threatLevel) {
        const colors = {
            'low': '#10b981',
            'medium': '#f59e0b',
            'high': '#ef4444',
            'critical': '#dc2626'
        };
        return colors[threatLevel] || '#6b7280';
    }

    getThreatEmoji(threatLevel) {
        const emojis = {
            'low': '🟢',
            'medium': '🟡',
            'high': '🔴',
            'critical': '🚨'
        };
        return emojis[threatLevel] || '⚪';
    }

    formatTimestamp(timestamp) {
        if (!timestamp) return 'Unknown';
        const date = new Date(timestamp);
        return date.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    getTimeAgo(timestamp) {
        if (!timestamp) return 'Unknown';

        const now = Date.now();
        const then = new Date(timestamp).getTime();
        const diffMs = now - then;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        return `${diffDays}d ago`;
    }

    updateLastUpdate() {
        const now = new Date();
        document.getElementById('lastUpdate').textContent = now.toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }

    showLoading(show) {
        const overlay = document.getElementById('loadingOverlay');
        overlay.style.display = show ? 'flex' : 'none';
    }
}

// Initialize the app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new DroneMap();
});
