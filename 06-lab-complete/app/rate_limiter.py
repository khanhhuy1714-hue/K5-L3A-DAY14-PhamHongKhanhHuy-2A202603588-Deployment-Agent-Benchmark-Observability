"""
Rate limiting (tiêu chí 7) — sliding window 60s lưu trên Redis (có fallback in-memory).
"""
from collections import defaultdict, deque
import threading
import time
import uuid

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60
_lock = threading.Lock()
_memory_windows: dict[str, deque[float]] = defaultdict(deque)


def _check_memory_limit(key: str, limit: int, now: float) -> None:
    with _lock:
        window = _memory_windows[key]
        cutoff = now - WINDOW_SECONDS
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) >= limit:
            retry_after = max(1, int(window[0] + WINDOW_SECONDS - now) + 1)
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )
        window.append(now)


def check_rate_limit(key: str) -> None:
    """Kiểm tra và ghi nhận request theo sliding window 60 giây."""
    limit = settings.rate_limit_per_minute
    now = time.time()
    cutoff = now - WINDOW_SECONDS

    if r is not None:
        redis_key = f"ratelimit:{key}"
        try:
            pipe = r.pipeline()
            pipe.zremrangebyscore(redis_key, "-inf", cutoff)
            pipe.zcard(redis_key)
            _, count = pipe.execute()

            if count >= limit:
                oldest = r.zrange(redis_key, 0, 0, withscores=True)
                oldest_ts = oldest[0][1] if oldest else now
                retry_after = max(1, int(oldest_ts + WINDOW_SECONDS - now) + 1)
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            member = f"{now}:{uuid.uuid4().hex}"
            pipe = r.pipeline()
            pipe.zadd(redis_key, {member: now})
            pipe.expire(redis_key, WINDOW_SECONDS + 5)
            pipe.execute()
            return
        except HTTPException:
            raise
        except Exception:
            pass

    _check_memory_limit(key, limit, now)
