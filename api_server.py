"""FastAPI backend for Sensia (replaces Streamlit UI)."""

from __future__ import annotations

import sensia_bootstrap  # noqa: F401 — UTF-8 console on Windows (import first)

import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

import therapist_core as core

load_dotenv()


def _safe_error_message(exc: BaseException) -> str:
    """API error text safe on Windows consoles and JSON responses."""
    return str(exc).encode("utf-8", errors="replace").decode("utf-8")

app = FastAPI(title="Sensia API", version="1.0.0")

_cors_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://localhost:8080,http://127.0.0.1:8080",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    reply: str
    turns: list[dict[str, str]]
    guardrail_triggered: bool = False
    guardrail_category: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    redis_active: bool


class TurnsResponse(BaseModel):
    session_id: str
    turns: list[dict[str, str]]


class MicChatResponse(BaseModel):
    duplicate: bool = False
    transcription: str | None = None
    reply: str | None = None
    turns: list[dict[str, str]] = []
    error: str | None = None
    guardrail_triggered: bool = False
    guardrail_category: str | None = None


class AudioAnalyzeResponse(BaseModel):
    duplicate: bool = False
    transcription: str | None = None
    reply: str | None = None
    elapsed_seconds: float | None = None
    turns: list[dict[str, str]] = []
    guardrail_triggered: bool = False
    guardrail_category: str | None = None


@app.get("/api/health")
def health() -> dict[str, Any]:
    status = core.redis_status()
    return {"ok": True, **status}


@app.post("/api/sessions", response_model=SessionResponse)
def create_session() -> SessionResponse:
    sid = core.create_session_id()
    status = core.redis_status()
    return SessionResponse(session_id=sid, redis_active=status["redis_active"])


@app.get("/api/sessions/{session_id}/turns", response_model=TurnsResponse)
def get_turns(session_id: str, limit: int = 100) -> TurnsResponse:
    return TurnsResponse(session_id=session_id, turns=core.list_turns(session_id, limit))


@app.post("/api/sessions/{session_id}/chat", response_model=ChatResponse)
def post_chat(session_id: str, body: ChatRequest) -> ChatResponse:
    try:
        outcome = core.chat_text(session_id, body.message.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_error_message(e)) from e
    return ChatResponse(
        reply=outcome.reply,
        turns=core.list_turns(session_id, 100),
        guardrail_triggered=outcome.guardrail_triggered,
        guardrail_category=outcome.guardrail_category,
    )


@app.post("/api/sessions/{session_id}/mic", response_model=MicChatResponse)
async def post_mic(session_id: str, file: UploadFile = File(...)) -> MicChatResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio upload")
    import hashlib

    sig = hashlib.sha256(data).hexdigest()
    try:
        result = core.chat_from_mic(session_id, data, sig)
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_error_message(e)) from e
    return MicChatResponse(
        duplicate=result.get("duplicate", False),
        transcription=result.get("transcription"),
        reply=result.get("reply"),
        turns=core.list_turns(session_id, 100),
        error=result.get("error"),
        guardrail_triggered=bool(result.get("guardrail_triggered", False)),
        guardrail_category=result.get("guardrail_category"),
    )


@app.post("/api/sessions/{session_id}/audio/analyze", response_model=AudioAnalyzeResponse)
async def post_audio_analyze(session_id: str, file: UploadFile = File(...)) -> AudioAnalyzeResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio file")
    import hashlib

    sig = hashlib.sha256(data).hexdigest()
    try:
        result = core.analyze_audio_upload(session_id, data, sig)
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_error_message(e)) from e
    if result.get("duplicate"):
        return AudioAnalyzeResponse(duplicate=True, turns=core.list_turns(session_id, 100))
    return AudioAnalyzeResponse(
        duplicate=False,
        transcription=result.get("transcription"),
        reply=result.get("reply"),
        elapsed_seconds=result.get("elapsed_seconds"),
        turns=core.list_turns(session_id, 100),
        guardrail_triggered=bool(result.get("guardrail_triggered", False)),
        guardrail_category=result.get("guardrail_category"),
    )


@app.post("/api/sessions/{session_id}/tts")
def post_tts(session_id: str, body: ChatRequest) -> Response:
    try:
        audio = core.text_to_speech_sync(body.message.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_error_message(e)) from e
    return Response(content=audio, media_type="audio/mpeg")


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, clear_file_log: bool = False) -> dict[str, str]:
    core.clear_session_data(session_id, clear_file_log=clear_file_log)
    return {"status": "cleared", "session_id": session_id}


@app.get("/api/sessions/{session_id}/summary")
def get_summary(session_id: str) -> dict[str, Any]:
    from conversation_store import get_session_summary

    return {"session_id": session_id, **get_session_summary(session_id)}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, reload=True)
