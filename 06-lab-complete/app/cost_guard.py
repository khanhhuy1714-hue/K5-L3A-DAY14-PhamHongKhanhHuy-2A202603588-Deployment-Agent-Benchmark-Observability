"""
Cost guard (tiêu chí 8) — theo dõi chi phí ngày/tháng trên Redis (fallback in-memory).
"""
from datetime import datetime, timezone
import threading

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

_lock = threading.Lock()
_memory_costs: dict[str, float] = {}


def _period_keys() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return (
        f"cost:daily:{now.strftime('%Y-%m-%d')}",
        f"cost:monthly:{now.strftime('%Y-%m')}",
    )


def _get_costs() -> tuple[float, float]:
    daily_key, monthly_key = _period_keys()
    if r is not None:
        try:
            daily = float(r.get(daily_key) or 0.0)
            monthly = float(r.get(monthly_key) or 0.0)
            return daily, monthly
        except Exception:
            pass
    with _lock:
        return _memory_costs.get(daily_key, 0.0), _memory_costs.get(monthly_key, 0.0)


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    daily_cost, monthly_cost = _get_costs()
    if daily_cost >= settings.daily_budget_usd or monthly_cost >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="Budget exceeded",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (input_tokens / 1000.0) * PRICE_INPUT_PER_1K + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    daily_key, monthly_key = _period_keys()

    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.incrbyfloat(daily_key, cost)
            pipe.expire(daily_key, 2 * 24 * 3600)
            pipe.incrbyfloat(monthly_key, cost)
            pipe.expire(monthly_key, 32 * 24 * 3600)
            pipe.execute()
            return cost
        except Exception:
            pass

    with _lock:
        _memory_costs[daily_key] = _memory_costs.get(daily_key, 0.0) + cost
        _memory_costs[monthly_key] = _memory_costs.get(monthly_key, 0.0) + cost
    return cost
