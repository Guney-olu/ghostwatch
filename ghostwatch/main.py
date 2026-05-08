"""GhostWatch — Maritime Intelligence System.

FastAPI application that serves the dashboard SPA and the detection,
telemetry, and command APIs from a single port.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ghostwatch import config
from ghostwatch.api.routes import router, init_services


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[GhostWatch] Starting up...")
    print(f"[GhostWatch] SimSat API: {config.SIMSAT_API_URL}")
    print(f"[GhostWatch] Model: {config.MODEL_ID}")
    print(f"[GhostWatch] Mock mode: {config.MOCK_MODE}")
    init_services()
    print("[GhostWatch] Ready.")
    yield
    print("[GhostWatch] Shutting down.")


app = FastAPI(
    title="GhostWatch",
    description="AI-powered dark vessel detection from satellite imagery",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


DIST = Path(__file__).parent / "frontend" / "dist"

if DIST.is_dir():
    app.mount("/static", StaticFiles(directory=DIST), name="static")
    cesium_dir = DIST / "cesium"
    if cesium_dir.is_dir():
        app.mount("/cesium", StaticFiles(directory=cesium_dir), name="cesium")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi"):
            raise HTTPException(status_code=404)
        return FileResponse(DIST / "index.html")
else:
    print(
        f"[GhostWatch] WARNING: {DIST} not found — frontend not built. "
        "Run `cd ghostwatch/frontend && npm install && npm run build`."
    )


if __name__ == "__main__":
    import os
    import uvicorn
    reload = os.getenv("GHOSTWATCH_RELOAD", "").lower() == "true"
    uvicorn.run(
        "ghostwatch.main:app" if reload else app,
        host=config.HOST,
        port=config.PORT,
        reload=reload,
    )
