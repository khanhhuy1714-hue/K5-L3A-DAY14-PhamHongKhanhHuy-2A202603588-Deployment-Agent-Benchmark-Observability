"""
Production AI Agent — Part 6 Final Project.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import sys
import time

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Định dạng mỗi dòng log thành một JSON object hợp lệ."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
        }
        for field in ("method", "path", "status", "ms", "environment", "in_flight", "cost_usd"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logger() -> logging.Logger:
    log = logging.getLogger("agent")
    log.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    log.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    log.addHandler(handler)
    log.propagate = False
    return log


logger = _configure_logger()
START_TIME = time.time()
_is_ready = False
_in_flight_requests = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    _is_ready = True
    logger.info("startup", extra={"event": "startup", "environment": settings.environment})
    try:
        yield
    finally:
        _is_ready = False
        logger.info("shutdown_started", extra={"event": "shutdown_started", "in_flight": _in_flight_requests})
        deadline = time.monotonic() + 8.0
        while _in_flight_requests > 0 and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        if r is not None:
            try:
                r.close()
            except Exception:
                pass
        logger.info("shutdown_complete", extra={"event": "shutdown_complete", "in_flight": _in_flight_requests})


app = FastAPI(title="Production AI Agent", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def request_tracking_and_logging(request: Request, call_next):
    global _in_flight_requests
    _in_flight_requests += 1
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        _in_flight_requests -= 1
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "request",
            extra={
                "event": "request",
                "method": request.method,
                "path": request.url.path,
                "status": status_code,
                "ms": duration_ms,
            },
        )


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None


@app.get("/")
def root():
    return {"service": "Production AI Agent", "environment": settings.environment}


@app.get("/health")
def health():
    """Liveness probe: luôn trả 200 khi process còn chạy."""
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "environment": settings.environment,
    }


@app.get("/ready")
def ready():
    """Readiness probe: 200 khi sẵn sàng và Redis kết nối được, ngược lại 503."""
    if not _is_ready or not redis_healthy():
        return JSONResponse(status_code=503, content={"status": "not ready"})
    return {"status": "ready", "redis": "ok"}


@app.post("/ask")
async def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()

    answer = await asyncio.to_thread(llm_ask, body.question)
    input_tokens = max(1, len(body.question.split()) * 2)
    output_tokens = max(1, len(answer.split()) * 2)
    cost = record_cost(input_tokens, output_tokens)

    return {
        "question": body.question,
        "answer": answer,
        "cost_usd": round(cost, 6),
    }
