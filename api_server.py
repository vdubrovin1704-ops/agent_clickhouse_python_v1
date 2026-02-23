"""
FastAPI сервер — HTTP endpoints для агента.
"""

import asyncio
import uuid
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import MODEL
from composite_agent import CompositeAnalysisAgent

app = FastAPI(title="ClickHouse Analysis Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = CompositeAnalysisAgent()


class AnalyzeRequest(BaseModel):
    query: str
    session_id: str | None = Field(default=None)


@app.get("/")
async def root():
    return {"status": "online", "model": MODEL}


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/info")
async def info():
    return {
        "service": "ClickHouse Analysis Agent",
        "version": "1.0.0",
        "model": MODEL,
        "features": [
            "clickhouse_query",
            "python_analysis",
            "matplotlib_charts",
            "chat_history",
        ],
    }


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    session_id = req.session_id or str(uuid.uuid4())
    result = await asyncio.to_thread(agent.analyze, req.query, session_id)
    result["timestamp"] = datetime.utcnow().isoformat()
    return result


@app.get("/api/chat-stats")
async def chat_stats():
    return agent.chat_storage.get_stats()


@app.on_event("startup")
async def startup():
    async def cleanup_loop():
        while True:
            await asyncio.sleep(1800)
            agent.chat_storage.cleanup_expired()
            agent.cleanup_temp_files()

    asyncio.create_task(cleanup_loop())
