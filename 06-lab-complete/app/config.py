"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.
"""
import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv(override=False)
except ImportError:
    pass


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


@dataclass
class Settings:
    port: int = _env_int("PORT", 8000)
    environment: str = os.getenv("ENVIRONMENT", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    agent_api_key: str = os.getenv("AGENT_API_KEY", "")
    redis_url: str = os.getenv("REDIS_URL", "")
    rate_limit_per_minute: int = _env_int("RATE_LIMIT_PER_MINUTE", 10)
    daily_budget_usd: float = _env_float("DAILY_BUDGET_USD", 1.0)
    monthly_budget_usd: float = _env_float("MONTHLY_BUDGET_USD", 10.0)


settings = Settings()
