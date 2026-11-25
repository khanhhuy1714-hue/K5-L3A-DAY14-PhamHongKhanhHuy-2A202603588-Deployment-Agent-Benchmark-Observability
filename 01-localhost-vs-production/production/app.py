"""
✅ ADVANCED — 12-Factor Compliant Agent

So sánh với basic/app.py để thấy sự khác biệt:
  ✅ Config từ environment variables
  ✅ Structured JSON logging
  ✅ Health check endpoint
  ✅ Graceful shutdown
  ✅ 0.0.0.0 binding (chạy được trong container)
  ✅ Port từ PORT env var (Railway/Render inject tự động)
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from contextlib import asynccontextmanager


from fastapi import FastAPI, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from config import settings
from utils.mock_llm import ask

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            **getattr(record, "fields", {}),
        }, ensure_ascii=False)


logger = logging.getLogger("day14.localhost_agent")
logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)
logger.propagate = False
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)

# Track startup time cho /health
START_TIME = time.time()
is_ready = False  # readiness flag


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    ✅ Lifecycle management:
    - startup: khởi tạo connections, load model
    - shutdown: đóng connections gracefully
    """
    global is_ready

    # --- Startup ---
    logger.info("startup", extra={"fields": {
        "app": settings.app_name,
        "version": settings.app_version,
        "env": settings.environment,
        "port": settings.port,
        "llm_backend": "mock",
    }})
    # Simulate loading model/connecting DB
    await asyncio.sleep(0.1)
    is_ready = True
    logger.info("ready")

    try:
        yield
    finally:
        # Uvicorn drains in-flight requests before lifespan shutdown.
        is_ready = False
        logger.info("shutdown_complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# ✅ CORS — chỉ cho phép origins được cấu hình
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/")
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "status": "running",
    }

# curl -X POST http://localhost:8000/ask \
#   -H "Content-Type: application/json" \
#   -d '{"question": "Hello"}'

@app.post("/ask")
async def ask_agent(request: Request):
    body = await request.json()
    question = body.get("question", "")

    if not question:
        raise HTTPException(status_code=422, detail="question field is required")

    # ✅ Structured logging — KHÔNG log secrets
    logger.info("agent_request", extra={"fields": {
        "question_length": len(question),
    }})

    response = await run_in_threadpool(ask, question)

    logger.info("agent_response", extra={"fields": {
        "response_length": len(response),
    }})

    return {
        "question": question,
        "answer": response,
        "model": settings.llm_model,
    }


# ============================================================
# HEALTH CHECK — Required for cloud deployment
# ============================================================

@app.get("/health")
def health_check():
    """
    ✅ Liveness probe: "Agent có còn sống không?"
    Platform gọi endpoint này định kỳ.
    Nếu trả về non-200 → platform restart container.
    """
    uptime = round(time.time() - START_TIME, 1)
    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready")
def readiness_check():
    """
    ✅ Readiness probe: "Agent có sẵn sàng nhận request chưa?"
    Load balancer dùng cái này để quyết định có route traffic vào không.
    Trả về 503 khi cờ readiness của lifecycle chưa bật.
    """
    if not is_ready:
        raise HTTPException(status_code=503, detail="Agent not ready yet")
    return {"ready": True}


@app.get("/metrics")
def metrics():
    """
    ✅ Basic metrics endpoint — có thể scrape bởi Prometheus.
    """
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "environment": settings.environment,
        "version": settings.app_version,
    }


if __name__ == "__main__":
    uvicorn.run(
        "app:app" if settings.debug else app,
        host=settings.host,   # ✅ 0.0.0.0 — nhận kết nối từ bên ngoài container
        port=settings.port,    # ✅ từ PORT env var
        reload=settings.debug, # ✅ reload chỉ khi DEBUG=true
    )
