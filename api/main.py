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
from api.routers import news as news_router
from api.routers import weekly as weekly_router
from api.routers import options as options_router
from api.routers import broker as broker_router
from api.routers import backtest as backtest_router
from api.routers import charts as charts_router
from api.routers import tws as tws_router


def _get_real_ip(request: Request) -> str:
    """Use X-Forwarded-For when behind Cloud Run's load balancer."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_get_real_ip)

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
app.include_router(news_router.router)
app.include_router(weekly_router.router)
app.include_router(options_router.router)
app.include_router(broker_router.router, prefix="/api/broker")
app.include_router(backtest_router.router)
app.include_router(charts_router.router)
app.include_router(tws_router.router)


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
            # News + PCR
            "/api/news/feed",
            "/api/news/{id}/pcr-history",
            "/api/news/{id}/related",
            # Weekly contrarian signals
            "/api/weekly/signals",
            "/api/weekly/signals/{ticker}/history",
            # Options screener
            "/api/options/screener",
            "/api/options/screener/{ticker}/history",
            "/api/options/overview",
            # Broker / trading (require X-Internal-Secret)
            "/api/broker/status",
            "/api/broker/balance",
            "/api/broker/positions",
            "/api/broker/orders",
            "/api/broker/order",
            "/api/broker/trades",
        ],
    }


@app.get("/health")
def health():
    from sqlalchemy import text
    from api.db import SessionLocal
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_status = "ok"
    except Exception as e:
        db_status = str(e)
    return {"status": "ok", "db": db_status}
