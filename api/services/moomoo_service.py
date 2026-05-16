"""
Singleton wrapper around MoomooClient for use inside FastAPI async handlers.

moomoo-api is synchronous; all calls are dispatched via asyncio.to_thread()
so the event loop is never blocked.

Requires Moomoo OpenD running locally:
  Download: https://www.moomoo.com/openapi/
  Default: 127.0.0.1:11111
  Set MOOMOO_PORT=11111 in .env to enable.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable

logger = logging.getLogger(__name__)

_moomoo = None   # module-level singleton; type: MoomooClient | None


def _make_moomoo():
    from brokers.moomoo import MoomooClient
    return MoomooClient()


def get_moomoo():
    """Return the module-level MoomooClient, connecting if needed. Raises on failure."""
    global _moomoo
    if _moomoo is None:
        _moomoo = _make_moomoo()
        if not _moomoo.connect():
            _moomoo = None
            raise RuntimeError(
                "Moomoo: connection failed — is OpenD running? "
                "Download from https://www.moomoo.com/openapi/ and check MOOMOO_PORT in .env"
            )
    return _moomoo


def reset_moomoo():
    """Force reconnect on next call."""
    global _moomoo
    if _moomoo is not None:
        try:
            _moomoo.disconnect()
        except Exception:
            pass
    _moomoo = None


async def moomoo_call(fn: Callable, *args: Any, **kwargs: Any) -> Any:
    """
    Run a blocking MoomooClient method in the default thread-pool executor.
    Retries once with a fresh connection if the first call raises.
    """
    try:
        client = get_moomoo()
        return await asyncio.to_thread(fn, *args, **kwargs)
    except Exception as exc:
        logger.warning("moomoo_call(%s) failed (%s) — resetting session", fn.__name__, exc)
        reset_moomoo()
        client = get_moomoo()
        return await asyncio.to_thread(fn, *args, **kwargs)


def moomoo_is_configured() -> bool:
    return bool(os.getenv("MOOMOO_PORT"))


def moomoo_is_simulate() -> bool:
    return os.getenv("MOOMOO_TRADE_ENV", "SIMULATE").upper() != "REAL"
