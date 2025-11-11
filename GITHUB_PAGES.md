# 🌐 GitHub Pages Deployment Guide

This guide will help you deploy Drone Map to GitHub Pages for a free, static website.

## Overview

The Drone Map project uses a hybrid architecture:
- **Frontend (GitHub Pages)**: Static HTML/CSS/JS site hosted on GitHub Pages
- **Backend (Optional)**: Python backend with Telegram bot and database (runs separately)

## Deployment Options

### Option 1: Static Demo (No Backend)
Deploy just the frontend with mock data - perfect for demonstrations.

### Option 2: Full Integration
Deploy frontend to GitHub Pages and connect it to your own backend API.

---

## 🚀 Option 1: Static Demo (Recommended for Quick Start)

### Step 1: Enable GitHub Pages

1. Go to your repository on GitHub
2. Click **Settings** → **Pages**
3. Under "Build and deployment":
   - **Source**: Select "GitHub Actions"
4. The site will auto-deploy when you push changes

### Step 2: Access Your Site

Your site will be available at:
```
https://[your-username].github.io/Drone-Map/
```

**That's it!** The static demo uses mock data and works without any backend.

### Features Available:
- ✅ Interactive map with Leaflet
- ✅ Mock drone sightings data
- ✅ Statistics dashboard
- ✅ Responsive design
- ✅ Auto-updates every 5 minutes (with new mock data)

---

## 🔧 Option 2: Full Integration with Backend

To connect the GitHub Pages frontend to real data, you need to run the backend separately.

### Step 1: Deploy the Backend

You can host the backend on:
- **Local machine** (for testing)
- **VPS/Cloud server** (DigitalOcean, AWS, Azure, etc.)
- **Heroku, Railway, Render** (Platform as a Service)
- **Docker container**

#### Example: Running Backend Locally

```bash
# Setup
python main.py --init-db
python main.py --generate-data 50

# Start the web API server
python web_server.py
```

The backend will run on `http://localhost:5000`

### Step 2: Configure Frontend API Endpoint

Edit `docs/assets/js/app.js` and update the API endpoint:

```javascript
getApiEndpoint() {
    // Replace with your backend URL
    return 'https://your-backend-url.com/api';
}
```

### Step 3: Enable CORS on Backend

The backend already has CORS enabled for GitHub Pages. If you deploy to a cloud server, make sure:

1. The backend is accessible via HTTPS
2. CORS is configured to allow your GitHub Pages domain
3. Firewall allows incoming connections on port 5000 (or your chosen port)

### Step 4: Push Changes

```bash
git add docs/assets/js/app.js
git commit -m "Configure backend API endpoint"
git push origin main
```

GitHub Actions will automatically redeploy your site.

---

## 🐳 Backend Deployment with Docker

### Using Docker Compose

```bash
# Build and run
docker-compose up -d

# Check logs
docker-compose logs -f
```

### Deploy to Cloud

1. **DigitalOcean App Platform**:
   - Connect your GitHub repo
   - Configure as Docker container
   - Set environment variables

2. **AWS ECS/Fargate**:
   - Push Docker image to ECR
   - Create ECS task definition
   - Deploy as Fargate service

3. **Railway/Render**:
   - Connect GitHub repo
   - Auto-deploys from Dockerfile

---

## 📊 Architecture Diagram

```
┌─────────────────────────────────────┐
│      GitHub Pages (Frontend)       │
│  https://you.github.io/Drone-Map   │
│                                     │
│  - HTML/CSS/JavaScript             │
│  - Leaflet Maps                    │
│  - Mock Data (default)             │
└──────────────┬──────────────────────┘
               │
               │ (Optional) API Calls
               ▼
┌─────────────────────────────────────┐
│    Backend Server (Self-hosted)    │
│     Your server / Cloud / VPS      │
│                                     │
│  - Flask Web API                   │
│  - Telegram Bot                    │
│  - SQLite Database                 │
│  - Real-time Data Processing       │
└─────────────────────────────────────┘
```

---

## 🔒 Security Considerations

### For GitHub Pages:
- ✅ HTTPS enabled by default
- ✅ No secrets in frontend code
- ✅ All API calls are public

### For Backend:
- 🔐 Use HTTPS (Let's Encrypt, Cloudflare)
- 🔐 Keep `.env` secure with bot tokens
- 🔐 Implement rate limiting
- 🔐 Use environment variables for secrets
- 🔐 Configure firewall rules

---

## 🎨 Customization

### Change Default Map Location

Edit `docs/assets/js/app.js`:

```javascript
initMap() {
    // Change center coordinates and zoom
    this.map = L.map('map').setView([YOUR_LAT, YOUR_LON], YOUR_ZOOM);
}
```

### Customize Styling

Edit `docs/assets/css/style.css` to change colors, fonts, layout, etc.

### Add Custom Domain

1. Create a file named `CNAME` in the `docs/` folder
2. Add your domain: `dronemap.yourdomain.com`
3. Configure DNS:
   ```
   Type: CNAME
   Name: dronemap
   Value: [your-username].github.io
   ```

---

## 🧪 Testing Locally

Test the GitHub Pages site locally:

```bash
# Navigate to docs folder
cd docs

# Start a local server (Python 3)
python -m http.server 8000

# Open browser
open http://localhost:8000
```

Or use any static file server:
```bash
# Using Node.js
npx serve docs

# Using PHP
php -S localhost:8000 -t docs
```

---

## 🐛 Troubleshooting

### Site not updating
- Check GitHub Actions tab for deployment status
- Clear browser cache (Ctrl+Shift+R / Cmd+Shift+R)
- Wait 5-10 minutes for propagation

### Maps not loading
- Check browser console for errors
- Verify Leaflet CDN is accessible
- Check internet connection

### API calls failing
- Verify backend is running
- Check CORS configuration
- Verify API endpoint URL in app.js
- Check browser network tab for errors

### 404 errors
- Ensure GitHub Pages is enabled in settings
- Verify source is set to "GitHub Actions"
- Check that docs/ folder exists in repository

---

## 📝 Environment Variables for Backend

If connecting to a backend, configure these:

```env
# .env file
TELEGRAM_BOT_TOKEN=your_bot_token
DATABASE_URL=sqlite:///drone_map.db
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
```

---

## 🔄 Continuous Deployment

Every push to `main` branch automatically:
1. Triggers GitHub Actions workflow
2. Builds and validates the site
3. Deploys to GitHub Pages
4. Updates live site (usually within 1-2 minutes)

---

## 📚 Additional Resources

- [GitHub Pages Documentation](https://docs.github.com/pages)
- [Leaflet Documentation](https://leafletjs.com/)
- [Flask CORS Documentation](https://flask-cors.readthedocs.io/)

---

## 💡 Tips

1. **Start with Option 1** (static demo) to see the site working immediately
2. **Add backend later** when you need real data and Telegram integration
3. **Use mock data** for demonstrations and testing
4. **Monitor GitHub Actions** for deployment status
5. **Test locally** before pushing to production

---

**Your site is now live on GitHub Pages! 🎉**

Visit: `https://[your-username].github.io/Drone-Map/`
