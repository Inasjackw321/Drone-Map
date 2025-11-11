# Drone Map - GitHub Pages Site

This directory contains the static website files for GitHub Pages deployment.

## Structure

```
docs/
├── index.html          # Main page
├── assets/
│   ├── css/
│   │   └── style.css   # Styling
│   └── js/
│       └── app.js      # Application logic
├── _config.yml         # GitHub Pages config
└── robots.txt          # SEO configuration
```

## Features

- **Interactive Map**: Real-time drone tracking visualization using Leaflet
- **Statistics Dashboard**: Live stats on drone activity
- **Responsive Design**: Works on desktop, tablet, and mobile
- **Mock Data Mode**: Runs standalone without backend for demos
- **API Integration Ready**: Can connect to backend API for real data

## Local Development

```bash
# Serve locally
cd docs
python -m http.server 8000

# Visit http://localhost:8000
```

## Deployment

This site automatically deploys to GitHub Pages via GitHub Actions when changes are pushed to the main branch.

**Live URL**: https://inasjackw321.github.io/Drone-Map/

## Customization

### Change API Endpoint

Edit `assets/js/app.js`:
```javascript
getApiEndpoint() {
    return 'https://your-backend-api.com/api';
}
```

### Modify Styling

Edit `assets/css/style.css` to customize colors, fonts, and layout.

### Update Map Center

Edit `assets/js/app.js`:
```javascript
this.map = L.map('map').setView([LAT, LON], ZOOM);
```

## Technologies Used

- **Leaflet.js**: Interactive maps
- **Leaflet.heat**: Heatmap visualization
- **Vanilla JavaScript**: No framework dependencies
- **CSS Grid/Flexbox**: Modern responsive layout
