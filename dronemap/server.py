"""HTTP API + static web app."""
from __future__ import annotations

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
