from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.app_router import api_router
from app.core.config import PROJECT_ROOT, settings
from app.core.ids import new_id
from app.core.logging import configure_logging, request_id_var
from app.db import init_db


_DEFAULT_CORS_ALLOWED_ORIGINS = (
    "http://127.0.0.1:4173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://localhost:5173",
)


def _cors_allowed_origins() -> list[str]:
    configured = [
        origin.strip().rstrip("/")
        for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
        if origin.strip() and origin.strip() != "*"
    ]
    return list(dict.fromkeys(configured or _DEFAULT_CORS_ALLOWED_ORIGINS))


def create_app() -> FastAPI:
    configure_logging("INFO")
    init_db()

    app = FastAPI(title="Learning Agent System", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    files_dir = settings.files_path
    exports_dir = settings.data_path / "exports"
    files_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    app.mount("/files", StaticFiles(directory=str(files_dir)), name="files")
    app.mount("/exports", StaticFiles(directory=str(exports_dir)), name="exports")

    logger = logging.getLogger("app.http")

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "request_id": request.headers.get("x-request-id") or new_id(),
                "success": False,
                "data": None,
                "error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)},
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled backend error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "request_id": request.headers.get("x-request-id") or new_id(),
                "success": False,
                "data": None,
                "error": {"code": "INTERNAL_SERVER_ERROR", "message": "后端服务异常，请查看日志定位原因。"},
            },
        )

    @app.middleware("http")
    async def request_log_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or new_id()
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            cost_ms = (time.perf_counter() - start) * 1000
            logger.info("%s %s %s %.1fms", request.method, request.url.path, response.status_code, cost_ms)
            response.headers["x-request-id"] = request_id
            return response
        except Exception:
            cost_ms = (time.perf_counter() - start) * 1000
            logger.exception("%s %s 500 %.1fms", request.method, request.url.path, cost_ms)
            raise
        finally:
            request_id_var.reset(token)

    @app.get("/health")
    async def health():
        return {"ok": True}

    frontend_dir = os.environ.get("FRONTEND_DIST")
    frontend_path = PROJECT_ROOT / "frontend-vue" / "dist" if not frontend_dir else Path(frontend_dir)
    if (frontend_path / "index.html").is_file():
        assets_path = frontend_path / "assets"
        if assets_path.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_path)), name="frontend-assets")

        @app.get("/{frontend_route:path}", include_in_schema=False)
        async def frontend(frontend_route: str):
            if frontend_route.startswith(("api/", "files/", "exports/")):
                raise HTTPException(status_code=404, detail="Not Found")
            if frontend_route == "favicon.svg" and (frontend_path / "favicon.svg").is_file():
                return FileResponse(frontend_path / "favicon.svg")
            if "." in frontend_route.rsplit("/", 1)[-1]:
                raise HTTPException(status_code=404, detail="Not Found")
            return FileResponse(frontend_path / "index.html")

    return app


app = create_app()
