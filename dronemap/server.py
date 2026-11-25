"""HTTP API + static web app."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .engine import Config, Engine

WEB = Path(__file__).resolve().parent.parent / "web"


def create_app(cfg: Config | None = None, on_ready=None) -> FastAPI:
    cfg = cfg or Config.from_env()
    engine = Engine(cfg)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await engine.start()
        if on_ready:
            on_ready()
        yield
        await engine.stop()

    app = FastAPI(title="Drone Map", lifespan=lifespan, docs_url="/api/docs", redoc_url=None)
    app.state.engine = engine

    @app.get("/api/state")
    async def state(request: Request):
        etag = f'W/"{engine.version}-{int(engine.snapshot.get("generated_at", 0)) // 5}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag})
        return JSONResponse(engine.snapshot, headers={"ETag": etag, "Cache-Control": "no-cache"})

    periods = {"24h": 24, "7d": 7 * 24, "28d": 28 * 24}

    @app.get("/api/heatmap")
    async def heatmap(period: str = "24h", kind: str = "all", tzo: int = 0, unconfirmed: int = 0):
        """Heatmap of reported drone and missile positions: period 24h | 7d | 28d,
        kind all | drone | missile | kab | explosion, tzo = the browser's getTimezoneOffset()."""
        hours = periods.get(period)
        if hours is None or kind not in ("all", "drone", "missile", "kab", "explosion"):
            return JSONResponse({"error": "period must be 24h, 7d or 28d; kind all, drone, missile, kab or explosion"},
                                status_code=400)
        view = await asyncio.to_thread(engine.heatmap_view, hours, kind, max(-840, min(840, tzo)), not unconfirmed)
        view["period"] = period
        return JSONResponse(view, headers={"Cache-Control": "no-cache"})

    @app.get("/api/sources")
    async def sources():
        return JSONResponse(engine.sources_view(), headers={"Cache-Control": "no-cache"})

    @app.get("/api/health")
    async def health():
        return engine.health()

    @app.get("/sw.js")
    async def sw():
        return FileResponse(WEB / "sw.js", media_type="application/javascript",
                            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})

    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
    return app
