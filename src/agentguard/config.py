"""Runtime settings, read once from the environment (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    paypal_client_id: str | None
    paypal_client_secret: str | None
    paypal_base_url: str
    anthropic_api_key: str | None
    agent_model: str
    agent_effort: str
    detector_model: str
    use_fallbacks: bool
    db_path: Path

    @property
    def paypal_mode(self) -> str:
        """`sandbox` when credentials are present, otherwise the offline simulator."""
        if os.getenv("PAYPAL_MODE") == "mock":
            return "mock"
        return "sandbox" if self.paypal_client_id and self.paypal_client_secret else "mock"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


def load_settings() -> Settings:
    return Settings(
        paypal_client_id=os.getenv("PAYPAL_CLIENT_ID") or None,
        paypal_client_secret=os.getenv("PAYPAL_CLIENT_SECRET") or None,
        paypal_base_url=os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        agent_model=os.getenv("AGENT_MODEL", "claude-opus-5-5"),
        agent_effort=os.getenv("AGENT_EFFORT", "medium"),
        detector_model=os.getenv("DETECTOR_MODEL", "claude-opus-5-5"),
        use_fallbacks=_flag("ANTHROPIC_FALLBACKS", True),
        db_path=Path(os.getenv("AGENTGUARD_DB", str(ROOT / "data" / "agentguard.db"))),
    )


settings = load_settings()
