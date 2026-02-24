"""
FastAPI сервер для комплексного агента
Предоставляет HTTP API и веб-интерфейс для работы с агентом
"""
import asyncio
import logging
import time
import traceback
import uuid
from datetime import datetime
from typing import Optional
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from composite_agent import CompositeAnalysisAgent

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Инициализация FastAPI
app = FastAPI(
    title="ClickHouse Analysis Agent API",
    description="Комплексный ИИ-агент для анализа данных из ClickHouse",
    version="1.0.0"
)

# CORS настройки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Таймаут агента (секунды)
AGENT_TIMEOUT = 240


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Логирование всех входящих HTTP-запросов"""
    start = time.time()
    response = await call_next(request)
    elapsed = round(time.time() - start, 1)
    logger.info(
        "📡 %s %s → %d (%.1fs)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed,
    )
    return response

# Глобальный экземпляр агента
agent = None


class AnalyzeRequest(BaseModel):
    """Запрос на анализ"""
    query: str
    session_id: Optional[str] = None


class AnalyzeResponse(BaseModel):
    """Ответ на запрос анализа"""
    success: bool
    session_id: str
    text_output: str
    plots: list[str]
    tool_calls: list[dict]
    error: Optional[str]
    timestamp: str


@app.on_event("startup")
async def startup():
    """Инициализация при запуске"""
    global agent
    try:
        agent = CompositeAnalysisAgent()
        logger.info("✅ Агент инициализирован")
    except Exception as e:
        logger.error("❌ Ошибка инициализации агента: %s", e)
        raise

    # Фоновая задача для очистки
    async def cleanup_loop():
        while True:
            await asyncio.sleep(1800)  # каждые 30 минут
            try:
                agent.chat_storage.cleanup_expired()
                agent.cleanup_temp_files()
            except Exception as e:
                logger.error("❌ Ошибка очистки: %s", e)

    asyncio.create_task(cleanup_loop())


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/status")
async def status():
    """API status"""
    return {
        "status": "online",
        "model": "Claude Sonnet 4",
        "service": "ClickHouse Analysis Agent"
    }


@app.get("/api/info")
async def info():
    """Информация о сервисе"""
    return {
        "version": "1.0.0",
        "model": "Claude Sonnet 4",
        "features": [
            "ClickHouse data extraction",
            "Python analysis with pandas/numpy",
            "Matplotlib/Seaborn visualizations",
            "Chat history with SQLite",
            "Parquet data format support"
        ],
        "tools": [
            "list_tables",
            "clickhouse_query",
            "python_analysis"
        ]
    }


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """
    Основной endpoint для анализа данных

    Принимает:
    - query: текстовый запрос пользователя
    - session_id: опционально, для продолжения диалога

    Возвращает:
    - success: флаг успешности
    - session_id: ID сессии
    - text_output: текстовый ответ агента
    - plots: список графиков в base64
    - tool_calls: список вызванных инструментов
    - error: текст ошибки (если есть)
    """
    if not agent:
        raise HTTPException(status_code=503, detail="Агент не инициализирован")

    # Генерация session_id если не передан
    session_id = request.session_id or str(uuid.uuid4())

    logger.info("📥 Запрос: session_id=%s query=%.80r", session_id, request.query)
    start = time.time()

    # Выполнение анализа в отдельном потоке (синхронный anthropic client)
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(agent.analyze, request.query, session_id),
            timeout=AGENT_TIMEOUT,
        )
        elapsed = round(time.time() - start, 1)
        logger.info(
            "✅ Ответ: session_id=%s success=%s tool_calls=%d plots=%d time=%.1fs",
            session_id,
            result.get("success"),
            len(result.get("tool_calls", [])),
            len(result.get("plots", [])),
            elapsed,
        )
        result["timestamp"] = datetime.now().isoformat()
        return result
    except asyncio.TimeoutError:
        elapsed = round(time.time() - start, 1)
        logger.error(
            "❌ Таймаут: session_id=%s time=%.1fs (лимит %ds)",
            session_id,
            elapsed,
            AGENT_TIMEOUT,
        )
        return JSONResponse(
            status_code=504,
            content={
                "success": False,
                "session_id": session_id,
                "text_output": "",
                "plots": [],
                "tool_calls": [],
                "error": f"Запрос превысил таймаут {AGENT_TIMEOUT} секунд. Попробуйте упростить запрос.",
                "timestamp": datetime.now().isoformat(),
            },
        )
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        logger.error(
            "❌ Ошибка: session_id=%s time=%.1fs error=%s\n%s",
            session_id,
            elapsed,
            e,
            traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chat-stats")
async def chat_stats():
    """Статистика по чатам"""
    if not agent:
        raise HTTPException(status_code=503, detail="Агент не инициализирован")

    try:
        stats = agent.chat_storage.get_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Монтирование статических файлов (веб-интерфейс)
# Должно быть в конце, чтобы не перехватывать API роуты
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        access_log=True
    )
