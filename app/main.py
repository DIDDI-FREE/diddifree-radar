from __future__ import annotations

import os
import secrets

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as pilotage_router
from app.core.db import init_db
from app.core.logging import Stopwatch, log_json
from app.core.request_context import set_request_id

init_db()

app = FastAPI(
    title="DiddiFree Pilotage API",
    description="Read-model service for management visibility: KPIs, freshness, alerts and deep links.",
    version="0.1.0",
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or f"req_{secrets.token_hex(8)}"
    set_request_id(request_id)
    timer = Stopwatch()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    log_json(
        {
            "event": "http_request",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": timer.elapsed_ms(),
        }
    )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("PILOTAGE_CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pilotage_router, prefix="/api")


@app.get("/health")
def container_health() -> dict:
    return {"module": "pilotage", "status": "healthy"}
