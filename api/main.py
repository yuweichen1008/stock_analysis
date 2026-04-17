"""
Oracle FastAPI backend — serves mobile app with prediction data, sandbox game, and push notifications.

Run:  uvicorn api.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import oracle, sandbox, signals, notify, subscribe, stocks, agents, graph

app = FastAPI(
    title="Oracle API",
    description="TAIEX Market Oracle — predictions, sandbox betting game, and push notifications",
    version="1.0.0",
)

# Allow all origins for local dev + Expo Go
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        "version": "1.0.0",
        "docs":    "/docs",
        "endpoints": [
            "/api/oracle/today",
            "/api/oracle/history",
            "/api/oracle/stats",
            "/api/oracle/live",
            "/api/signals/tw",
            "/api/signals/us",
            "/api/sandbox/register",
            "/api/sandbox/me/{device_id}",
            "/api/sandbox/bet",
            "/api/sandbox/leaderboard",
            "/api/notify/register",
            "/api/notify/broadcast",
            "/api/subscribe",
            "/subscribe",
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
