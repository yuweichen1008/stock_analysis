"""
Oracle FastAPI backend — serves mobile app with prediction data, sandbox game, and push notifications.

Run:  uvicorn api.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from api.config import settings
from api.routers import oracle, sandbox, signals, notify, subscribe, stocks, agents, graph
from api.routers import auth as auth_router
from api.routers import watchlist as watchlist_router
from api.routers import feed as feed_router

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Oracle API",
    description="TAIEX Market Oracle — predictions, sandbox betting game, and push notifications",
    version="2.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — use configured origins (or "*" in dev)
origins = settings.allowed_origins_list()
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router.router)
app.include_router(watchlist_router.router)
app.include_router(feed_router.router)
app.include_router(oracle.router)
app.include_router(sandbox.router)
app.include_router(signals.router)
app.include_router(notify.router)
app.include_router(subscribe.router)
app.include_router(stocks.router)
app.include_router(agents.router)
app.include_router(graph.router)


@app.get("/")
def root():
    return {
        "service": "Oracle API",
        "version": "2.0.0",
        "docs":    "/docs",
        "endpoints": [
            # Auth
            "/api/auth/apple",
            "/api/auth/google",
            "/api/auth/device",
            # Social
            "/api/watchlist",
            "/api/watchlist/alerts",
            "/api/feed",
            # Oracle
            "/api/oracle/today",
            "/api/oracle/history",
            "/api/oracle/stats",
            "/api/oracle/live",
            # Signals
            "/api/signals/tw",
            "/api/signals/us",
            "/api/signals/search",
            # Sandbox game
            "/api/sandbox/register",
            "/api/sandbox/me",
            "/api/sandbox/me/{device_id}",
            "/api/sandbox/bet",
            "/api/sandbox/leaderboard",
            # Internal (require X-API-Secret)
            "/api/sandbox/settle",
            "/api/notify/broadcast",
            "/api/stocks/settle",
            # Agents + graph
            "/api/agents/analyze",
            "/api/agents/batch",
            "/api/graph/signals",
            "/api/graph/sectors",
            "/api/graph/agents",
        ],
    }


@app.get("/health")
def health():
    return {"status": "ok"}
