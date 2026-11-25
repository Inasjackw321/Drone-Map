from fastapi.testclient import TestClient

from dronemap.engine import Config
from dronemap.server import create_app


def test_api_and_static_in_demo_mode():
    app = create_app(Config(mode="demo"))
    with TestClient(app) as c:
        app.state.engine.rebuild()
        r = c.get("/api/state")
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "demo" and body["tracks"]
        etag = r.headers["etag"]
        assert c.get("/api/state", headers={"If-None-Match": etag}).status_code == 304

        src = c.get("/api/sources").json()
        assert [g["tier"] for g in src["groups"]] == ["official", "recon", "regional", "aggregator"]
        assert sum(len(g["channels"]) for g in src["groups"]) >= 80

        assert c.get("/api/health").json()["ok"]
        for period in ("24h", "7d", "28d"):
            h = c.get(f"/api/heatmap?period={period}&kind=all&tzo=-120")
            assert h.status_code == 200 and h.json()["period"] == period
        week = c.get("/api/heatmap?period=7d&kind=drone").json()
        assert week["observations"] > 0 and week["points"] and week["by_oblast"]
        assert c.get("/api/heatmap?period=1y").status_code == 400
        assert c.get("/api/heatmap?kind=cars").status_code == 400
        page = c.get("/")
        assert page.status_code == 200 and "Drone Map" in page.text
        assert c.get("/sw.js").status_code == 200
        assert c.get("/manifest.webmanifest").status_code == 200
