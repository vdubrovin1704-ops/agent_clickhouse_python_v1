import asyncio
from datetime import datetime
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from composite_agent import CompositeAnalysisAgent
from config import SERVER_URL


agent = CompositeAnalysisAgent()
app = FastAPI(title="ClickHouse + Python Analysis Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    query: str
    session_id: str | None = None


@app.get("/")
async def root():
    return {"status": "online", "model": "Claude Sonnet 4", "server": SERVER_URL}


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/info")
async def api_info():
    return {
        "success": True,
        "service": "ClickHouse Analysis Agent",
        "version": "1.0.0",
        "model": "Claude Sonnet 4",
        "features": [
            "ClickHouse SQL queries",
            "Python analysis with plots",
            "Session-based chat history",
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest):
    session_id = request.session_id or str(uuid.uuid4())
    result = await asyncio.to_thread(agent.analyze, request.query, session_id)
    result["timestamp"] = datetime.utcnow().isoformat()
    return result


@app.get("/api/chat-stats")
async def chat_stats():
    stats = agent.chat_storage.get_stats()
    stats["timestamp"] = datetime.utcnow().isoformat()
    return stats


@app.on_event("startup")
async def startup():
    async def cleanup_loop():
        while True:
            await asyncio.sleep(1800)
            agent.chat_storage.cleanup_expired()
            agent.cleanup_temp_files()

    asyncio.create_task(cleanup_loop())


if __name__ == "__main__":
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=False)
