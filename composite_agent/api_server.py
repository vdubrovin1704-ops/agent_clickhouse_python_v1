"""
FastAPI сервер для CompositeAnalysisAgent.
Предназначен для будущей интеграции с веб-интерфейсом.
Запуск: uvicorn api_server:app --host 0.0.0.0 --port 8000
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from composite_agent import CompositeAnalysisAgent

# Глобальный экземпляр агента
agent: CompositeAnalysisAgent | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация и очистка при запуске/остановке сервера."""
    global agent
    agent = CompositeAnalysisAgent()

    async def cleanup_loop():
        while True:
            await asyncio.sleep(1800)  # каждые 30 минут
            try:
                agent.chat_storage.cleanup_expired()
                agent.cleanup_temp_files()
            except Exception:
                pass

    task = asyncio.create_task(cleanup_loop())
    yield
    task.cancel()


app = FastAPI(title="ClickHouse Analysis Agent", version="1.0.0", lifespan=lifespan)

# Настроить CORS под конкретные домены в продакшене
# allow_credentials=True несовместим с allow_origins=["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request / Response schemas ───────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    query: str
    session_id: str | None = None


class AnalyzeResponse(BaseModel):
    success: bool
    session_id: str
    text_output: str
    plots: list[str]
    tool_calls: list[dict]
    error: str | None
    timestamp: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "online", "model": "Claude Sonnet"}


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/info")
async def info():
    return {
        "version": "1.0.0",
        "model": "claude-sonnet-4-5",
        "features": ["clickhouse_query", "python_analysis", "matplotlib_plots", "chat_history"],
    }


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    session_id = req.session_id or str(uuid.uuid4())

    # Запустить синхронный агент в thread pool (не блокирует event loop)
    result = await asyncio.to_thread(agent.analyze, req.query, session_id)

    return AnalyzeResponse(
        success=result["success"],
        session_id=result["session_id"],
        text_output=result.get("text_output", ""),
        plots=result.get("plots", []),
        tool_calls=result.get("tool_calls", []),
        error=result.get("error"),
        timestamp=datetime.utcnow().isoformat(),
    )


@app.get("/api/chat-stats")
async def chat_stats():
    return agent.chat_storage.get_stats()
