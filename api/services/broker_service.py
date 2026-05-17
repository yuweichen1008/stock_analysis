"""
Singleton wrapper around CTBCClient for use inside FastAPI async handlers.

Playwright is synchronous; all calls are dispatched via asyncio.to_thread()
so the event loop is never blocked. The singleton reconnects automatically
when the session expires.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable

logger = logging.getLogger(__name__)

_ctbc = None   # module-level singleton; type: CTBCClient | None


def _make_ctbc():
    from brokers.ctbc import CTBCClient
    return CTBCClient()


def get_ctbc():
    """Return the module-level CTBCClient, connecting if needed. Raises on failure."""
    global _ctbc
    if _ctbc is None:
        _ctbc = _make_ctbc()
        if not _ctbc.connect():
            _ctbc = None
            raise RuntimeError("CTBC: login failed — check CTBC_ID / CTBC_PASSWORD in .env")
    return _ctbc


def reset_ctbc():
    """Force reconnect on next call (e.g. after session expiry)."""
    global _ctbc
    if _ctbc is not None:
        try:
            _ctbc.disconnect()
        except Exception:
            pass
    _ctbc = None


async def ctbc_call(fn: Callable, *args: Any, **kwargs: Any) -> Any:
    """
    Run a blocking CTBCClient method in the default thread-pool executor.
    Retries once with a fresh connection if the first call raises.
    """
    try:
        client = get_ctbc()
        return await asyncio.to_thread(fn, *args, **kwargs)
    except Exception as exc:
        # Session may have expired — try once more with a fresh login
        logger.warning("ctbc_call(%s) failed (%s) — resetting session", fn.__name__, exc)
        reset_ctbc()
        client = get_ctbc()
        return await asyncio.to_thread(fn, *args, **kwargs)


def ctbc_is_configured() -> bool:
    return bool(os.getenv("CTBC_ID") and os.getenv("CTBC_PASSWORD"))


def ctbc_is_dry_run() -> bool:
    return os.getenv("CTBC_DRY_RUN", "true").lower() != "false"


def make_ctbc_for_user(user) -> "CTBCClient":
    """Return a CTBCClient using the user's encrypted credentials (or env fallback)."""
    from brokers.ctbc import CTBCClient
    from api.auth import decrypt_cred
    if user and user.ctbc_id_enc and user.ctbc_pass_enc:
        return CTBCClient(
            id=decrypt_cred(user.ctbc_id_enc),
            password=decrypt_cred(user.ctbc_pass_enc),
            profile_suffix=str(user.id),
        )
    return CTBCClient()


async def ctbc_call_for_user(user, fn: Callable, *args: Any, **kwargs: Any) -> Any:
    """Like ctbc_call but uses the user's own credentials (no shared singleton)."""
    client = make_ctbc_for_user(user)
    if not client.connect():
        raise RuntimeError("CTBC: login failed — check credentials")
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    finally:
        try:
            client.disconnect()
        except Exception:
            pass
