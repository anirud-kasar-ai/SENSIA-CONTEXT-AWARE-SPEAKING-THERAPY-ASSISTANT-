"""Therapist RAG + Redis conversation logic (no Streamlit)."""

from __future__ import annotations

import sensia_bootstrap  # noqa: F401

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any

import nest_asyncio
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.prompts import PromptTemplate

from Audio_Analysis import analyze_with_openai, extract_audio_features
from chat_config import get_chat_llm
from conversation_store import (
    append_turn as store_append_turn,
    clear_session as store_clear_session,
    get_recent_turns,
    get_session_summary,
    get_turn_count,
    get_turns_slice,
    is_redis_active,
    set_session_summary,
)
from embeddings_config import get_embedding_model
from sensia_guardrails import GuardrailResult, evaluate_user_message, guardrails_enabled

load_dotenv()

GUARDRAIL_SCOPE_RULES = """
- You are an emotional-support companion for this session only—not a general assistant.
- Do NOT answer politics, government, elections, news, celebrities, trivia, homework, coding, legal, or medical-diagnosis questions.
- If the user asks something off-topic, reply only with: "I'm not able to help with that. I'm here only for emotional support and conversation in this session." Do not add facts.
"""


@dataclass
class AskOutcome:
    reply: str
    guardrail_triggered: bool = False
    guardrail_category: str | None = None
nest_asyncio.apply()

CHROMA_DB_DIR = "New_DB"
LOG_FILE = "conversation_log.txt"
MAX_HISTORY_TURNS = 30
SUMMARY_BATCH_TURNS = max(1, int(os.getenv("SENSIA_SUMMARY_BATCH", "5")))

logger = logging.getLogger(__name__)

_vectordb: Chroma | None = None
_processed_audio_sigs: dict[str, set[str]] = {}
_processed_mic_sigs: dict[str, set[str]] = {}

custom_prompt = PromptTemplate(
    input_variables=["context", "question"],
    template="""
---

You are a licensed mental health professional chatbot.

- When the user greets or introduces themselves (e.g., "hi," "hello, I am Sam"), respond with a short, warm, and welcoming message that gently invites them to share what's on their mind—without going too deep.
- If the user does NOT share their name, kindly ask for it once in a warm and respectful way, before continuing the conversation.
- Never guess or make up a name. Only use the user's name if they clearly tell you (e.g., "I'm Maria" or "My name is John").
- **One person per chat session:** The conversation history is always the same individual. Do **not** ask whether they are "someone new" versus someone from earlier in the thread, and do **not** frame the situation as two different people unless they explicitly say another person is present or they are not the same user.
- **Name across the session:** Infer their **preferred name** from the thread. If they correct or clarify their name (e.g., a typo, nickname, or "my name is actually …"), treat the **latest clear statement** as authoritative and use **only** that name from then on. Do not revert to an older mistaken name after they have corrected it.
- If a prior message used a different name but the user has since clearly identified themselves, acknowledge the correction briefly if helpful, then continue using the corrected name—stay consistent for the rest of the session.
- When the user ends the conversation (e.g., "thank you," "bye," "that's all for now"), respond with a brief, supportive closing message.
- When the user expresses readiness to continue, using phrases like "yes, please go ahead", "sure, continue", "please proceed", etc., continue the conversation concisely **without repeating previous greetings**.
- When the user declines a suggestion or sets a boundary (e.g., "no thanks," "not right now"), respond respectfully, acknowledge it, and offer a gentle closing or next step.
- For all other messages, generate a concise, warm, and helpful response based on the context and your professional understanding.
- Avoid clinical jargon. Be clear, compassionate, and to the point.
""" + GUARDRAIL_SCOPE_RULES + """

---

**Context (including chat history and related information):**
{context}

---

**User's input:**
{question}

---

**Your response (concise, empathic, professional, helpful):**
""",
)


def get_vectordb() -> Chroma:
    global _vectordb
    if _vectordb is None:
        embeddings = get_embedding_model()
        _vectordb = Chroma(persist_directory=CHROMA_DB_DIR, embedding_function=embeddings)
    return _vectordb


def create_session_id() -> str:
    return str(uuid.uuid4())


def redis_status() -> dict[str, Any]:
    return {"redis_active": is_redis_active()}


def log_interaction(user_input: str, gpt_response: str, log_file: str = LOG_FILE) -> None:
    entry = {
        "id": str(uuid.uuid4()),
        "user_input": user_input,
        "gpt_response": gpt_response,
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def build_formatted_history(session_id: str) -> str:
    turns = get_recent_turns(session_id, MAX_HISTORY_TURNS)
    return "\n".join([f"User: {t['user']}\nAssistant: {t['bot']}" for t in turns])


def append_conversation(session_id: str, user_text: str, bot_text: str) -> None:
    store_append_turn(session_id, user_text, bot_text)
    log_interaction(user_text, bot_text)


def merge_summarize_turn_batch(prior_summary: str, batch: list[dict[str, str]]) -> str:
    lines = []
    for t in batch:
        lines.append(f"User: {t['user']}\nAssistant: {t['bot']}")
    chunk = "\n\n".join(lines)
    prior = (prior_summary or "").strip()
    instructions = (
        "You update a concise session memory for a mental-health support chatbot. "
        "Use neutral, clinical-styled notes (short bullets or brief paragraphs). "
        "Preserve user-stated names, concerns, emotions, goals, and boundaries. "
        "Do not invent facts. If the new exchanges contradict older memory, prefer the newer information. "
        "Omit or minimize off-topic exchanges (e.g. politics trivia or guardrail refusals); focus on emotional support content."
    )
    prompt = (
        f"{instructions}\n\n"
        f"--- Prior session memory (may be empty) ---\n"
        f"{prior if prior else '(none)'}\n\n"
        f"--- New exchanges to fold in ({len(batch)} turns) ---\n"
        f"{chunk}\n\n"
        f"--- Task ---\n"
        f"Write the full updated session memory (not a preamble). "
        f"Do not address the user directly; this is internal context only."
    )
    summarizer = get_chat_llm(temperature=0.2)
    out = summarizer.invoke(prompt)
    return (out.content or "").strip()


def maybe_refresh_session_summary(session_id: str) -> None:
    batch_size = SUMMARY_BATCH_TURNS
    while True:
        total = get_turn_count(session_id)
        state = get_session_summary(session_id)
        cursor = int(state["cursor"])
        if total - cursor < batch_size:
            break
        batch = get_turns_slice(session_id, cursor, batch_size)
        if len(batch) < batch_size:
            break
        try:
            new_text = merge_summarize_turn_batch(str(state.get("text", "")), batch)
            set_session_summary(session_id, new_text, cursor + batch_size)
        except Exception as e:
            logger.warning("Session summary refresh failed: %s", e)
            break


def _outcome_from_guardrail(gr: GuardrailResult, user_message: str, session_id: str) -> AskOutcome:
    append_conversation(session_id, user_message, gr.reply)
    return AskOutcome(
        reply=gr.reply,
        guardrail_triggered=True,
        guardrail_category=gr.category,
    )


def ask_question(user_message: str, psychological_report: str, session_id: str) -> AskOutcome:
    if guardrails_enabled():
        gr = evaluate_user_message(user_message)
        if gr.action == "block":
            return _outcome_from_guardrail(gr, user_message, session_id)

    vectordb = get_vectordb()
    retriever = vectordb.as_retriever(search_kwargs={"k": 3})
    llm = get_chat_llm(temperature=0.3)
    formatted_history = build_formatted_history(session_id)
    summary_state = get_session_summary(session_id)
    summary_text = (summary_state.get("text") or "").strip()

    report = (psychological_report or "").strip()
    if report:
        system_context = f"""
        # System Instructions
        Below is a psychological assessment that provides insights into the user's emotional and mental state.
        Use this to guide your tone, empathy, and response style.
        Do NOT quote or restate this directly to the user — it is for your background understanding only.

        --- Psychological Assessment ---
        {report}
        {GUARDRAIL_SCOPE_RULES}
        """
    else:
        system_context = f"""
        # System Instructions
        There is no separate voice-based psychological assessment for this turn.
        Use the conversation history and retrieved context to respond empathetically and professionally.
        {GUARDRAIL_SCOPE_RULES}
        """

    memory_block = ""
    if summary_text:
        memory_block = (
            "\n\n--- Session memory summarized from earlier exchanges ---\n"
            "The following is an internal compressed memory of older turns. "
            "Do not quote it verbatim to the user; use it only for continuity and context.\n"
            f"{summary_text}\n"
        )

    docs = retriever.invoke(user_message)
    retrieved_context = "\n".join([doc.page_content for doc in docs])
    full_context = (
        f"{system_context}\n\n--- Retrieved Context ---\n{retrieved_context}\n"
        f"{memory_block}\n"
        f"--- Conversation History ---\n{formatted_history}"
    )
    prompt_with_context = custom_prompt.format(context=full_context, question=user_message)
    response = llm.invoke(prompt_with_context)
    reply = response.content or ""
    append_conversation(session_id, user_message, reply)
    maybe_refresh_session_summary(session_id)
    return AskOutcome(reply=reply, guardrail_triggered=False, guardrail_category=None)


def list_turns(session_id: str, limit: int = 100) -> list[dict[str, str]]:
    return get_recent_turns(session_id, limit)


def clear_session_data(session_id: str, clear_file_log: bool = False) -> None:
    store_clear_session(session_id)
    _processed_audio_sigs.pop(session_id, None)
    _processed_mic_sigs.pop(session_id, None)
    if clear_file_log:
        open(LOG_FILE, "w", encoding="utf-8").close()


def transcribe_audio_file(file_path: str, model_size: str = "base", device: str = "cpu") -> str:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device=device)
    segments, _ = model.transcribe(file_path)
    return " ".join(segment.text for segment in segments)


async def text_to_speech_bytes(text: str) -> bytes:
    import edge_tts
    import tempfile

    communicate = edge_tts.Communicate(text, voice="en-US-JennyNeural", rate="+15%")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        path = tmp.name
    await communicate.save(path)
    with open(path, "rb") as f:
        data = f.read()
    try:
        os.unlink(path)
    except OSError:
        pass
    return data


def text_to_speech_sync(text: str) -> bytes:
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(text_to_speech_bytes(text))


def chat_text(session_id: str, message: str) -> AskOutcome:
    return ask_question(message, "", session_id)


def chat_from_mic(session_id: str, audio_bytes: bytes, content_sig: str) -> dict[str, Any]:
    import hashlib
    import tempfile

    sig = content_sig or hashlib.sha256(audio_bytes).hexdigest()
    seen = _processed_mic_sigs.setdefault(session_id, set())
    if sig in seen:
        return {"duplicate": True, "reply": None, "transcription": None}

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        transcription = transcribe_audio_file(tmp_path).strip()
        if not transcription:
            return {"duplicate": False, "reply": None, "transcription": "", "error": "no_speech"}
        outcome = ask_question(transcription, "", session_id)
        seen.add(sig)
        return {
            "duplicate": False,
            "reply": outcome.reply,
            "transcription": transcription,
            "guardrail_triggered": outcome.guardrail_triggered,
            "guardrail_category": outcome.guardrail_category,
        }
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def analyze_audio_upload(session_id: str, file_bytes: bytes, content_sig: str) -> dict[str, Any]:
    import hashlib
    import tempfile
    import time

    import librosa

    sig = content_sig or hashlib.sha256(file_bytes).hexdigest()
    seen = _processed_audio_sigs.setdefault(session_id, set())
    if sig in seen:
        return {"duplicate": True}

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        start = time.time()
        y, sr = librosa.load(tmp_path, sr=None)
        transcription = transcribe_audio_file(tmp_path)
        features = extract_audio_features(y, sr)
        psychological_report = analyze_with_openai(transcription, features)
        outcome = ask_question(transcription, psychological_report, session_id)
        seen.add(sig)
        return {
            "duplicate": False,
            "transcription": transcription,
            "reply": outcome.reply,
            "elapsed_seconds": round(time.time() - start, 2),
            "psychological_report": psychological_report,
            "guardrail_triggered": outcome.guardrail_triggered,
            "guardrail_category": outcome.guardrail_category,
        }
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
