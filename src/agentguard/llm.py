"""Shared Anthropic client with the defaults every call site uses."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

import anthropic

from .config import settings

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
_fallbacks_ok = settings.use_fallbacks


@lru_cache(maxsize=1)
def client() -> anthropic.Anthropic:
    # Pin the public endpoint so a stray ANTHROPIC_BASE_URL in the shell can't redirect calls.
    base_url = os.getenv("AGENTGUARD_ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, base_url=base_url, max_retries=3)


def _with_fallbacks(kwargs: dict[str, Any]) -> dict[str, Any]:
    if not _fallbacks_ok:
        return kwargs
    return {**kwargs, "betas": [*kwargs.get("betas", []), FALLBACK_BETA], "fallbacks": "default"}


def _call(method, kwargs: dict[str, Any]):
    """Run a beta messages call, with server-side refusal fallbacks when the API accepts them."""
    global _fallbacks_ok
    try:
        return method(**_with_fallbacks(kwargs))
    except anthropic.BadRequestError as exc:
        if _fallbacks_ok and "fallback" in str(exc).lower():
            log.warning("Refusal fallbacks rejected by the API; continuing without them.")
            _fallbacks_ok = False
            return method(**kwargs)
        raise


def create(**kwargs: Any):
    return _call(client().beta.messages.create, kwargs)


def parse(**kwargs: Any):
    return _call(client().beta.messages.parse, kwargs)
