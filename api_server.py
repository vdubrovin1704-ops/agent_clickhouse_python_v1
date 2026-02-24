"""
FastAPI сервер для комплексного агента (ОПЦИОНАЛЬНО)
Этот файл можно использовать для создания HTTP API в будущем
"""
import asyncio
import uuid
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from composite_agent import CompositeAnalysisAgent

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
        print("✅ Агент инициализирован")
    except Exception as e:
        print(f"❌ Ошибка инициализации агента: {e}")
        raise

    # Фоновая задача для очистки
    async def cleanup_loop():
        while True:
            await asyncio.sleep(1800)  # каждые 30 минут
            try:
                agent.chat_storage.cleanup_expired()
                agent.cleanup_temp_files()
            except Exception as e:
                print(f"❌ Ошибка очистки: {e}")

    asyncio.create_task(cleanup_loop())


@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "online",
        "model": "Claude Sonnet 4",
        "service": "ClickHouse Analysis Agent"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
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

    # Выполнение анализа в отдельном потоке (синхронный anthropic client)
    try:
        result = await asyncio.to_thread(agent.analyze, request.query, session_id)
        result["timestamp"] = datetime.now().isoformat()
        return result
    except Exception as e:
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        access_log=True
    )
