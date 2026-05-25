# 🧠 AI Therapist - Voice-Based Mental Health Support System

A Streamlit-based AI therapist that analyzes audio input to provide empathetic, context-aware mental health support using speech analysis, LangChain RAG, **Groq** (LLM chat), **sentence-transformers** (embeddings / Chroma), and Edge TTS.

## 📋 Features

- **Voice-based interaction**: Upload audio files (WAV/MP3) for analysis
- **Speech feature extraction**: Analyzes pitch, tone, speech rate, pauses, and emotional indicators using Librosa
- **Psychological assessment**: Generates clinical reports based on audio features and transcription (via Groq)
- **RAG-powered responses**: Uses vector database to provide contextually relevant therapeutic responses
- **Conversation logging**: Tracks all interactions for continuity
- **Text-to-speech responses**: Returns audio responses using Edge TTS
- **Text chat tab**: Same RAG + Groq pipeline as audio (no voice assessment for text-only turns)
- **Redis (optional)**: Persists per-session conversation turns for context across refreshes; falls back to in-memory if Redis is down or unset

## ⚙️ Requirements

- Python 3.11+
- **Groq API key** (`GROQ_API_KEY` in `.env`) for chat completions
- **Redis** (optional): `REDIS_URL` (e.g. `redis://localhost:6379/0`). If Redis is unavailable, the app still runs with in-memory history for the current process.
- First run downloads the HuggingFace embedding model (`sentence-transformers/all-mpnet-base-v2`); internet required once

### Run Redis locally (Docker)

```bash
docker run -d --name sensia-redis -p 6379:6379 redis:7-alpine
```

Then set `REDIS_URL=redis://localhost:6379/0` in `.env`.


## 🚀 Setup Instructions

### 1. Install Dependencies

pip install -r requirements.txt

### 2. Set up Environment Variables

Create a `.env` file in the project root:

GROQ_API_KEY=your_groq_api_key_here

Optional:

GROQ_MODEL=llama-3.3-70b-versatile

Redis (persistent chat context across browser refreshes for the same session ID):

REDIS_URL=redis://localhost:6379/0

Optional: `REDIS_CHAT_TTL` (seconds), `REDIS_KEY_PREFIX`, or `REDIS_DISABLED=1` to force in-memory store.

**Guardrails** (off-topic refusal, crisis helplines — enabled by default):

```env
SENSIA_GUARDRAILS_ENABLED=1
SENSIA_CRISIS_REGION=IN
```

- `SENSIA_CRISIS_REGION`: `IN` (default), `US`, or `UK` — crisis reply helpline text
- Tune keyword lists in [`guardrails_policy.json`](guardrails_policy.json) without code changes
- Set `SENSIA_GUARDRAILS_ENABLED=0` to disable input guardrails (prompt rules still apply)

Run guardrail tests: `python -m pytest tests/test_guardrails.py -q`

Architecture diagrams: [`Sensia-HLD.drawio`](Sensia-HLD.drawio), [`Sensia-LLD.drawio`](Sensia-LLD.drawio), [`Sensa flow diagam.drawio`](Sensa%20flow%20diagam.drawio) — input is checked by `sensia_guardrails.py` before `ask_question` in [`therapist_core.py`](therapist_core.py).


### 3. Create Vector Database

**Run this FIRST** before using the therapist:

streamlit run create_db.py


1. Upload your `data.jsonl` file (training data for therapeutic responses)
2. Click "Create Chroma Vector DB"
3. Wait for processing to complete
4. The database will be saved to the `New_DB/` directory


## 💬 Usage

### Run the AI Therapist

streamlit run AI_Therapist.py

Use the **Audio** tab for voice uploads or the **Text chat** tab for typed messages. The sidebar shows the active **session ID** (paste a previous ID and click **Apply** to resume that Redis-backed thread). **Clear session history** removes turns for the current session from Redis (and optionally clears `conversation_log.txt` if checked).

### Test with Sample Audio Files

Upload audio files in sequence (e.g., `hello.wav`, `1.wav`, `2.wav`, `3.wav`, `4.wav`, `5.wav`):

1. **Upload audio file** via the file uploader
2. **Wait for analysis**: The system will:
   - Transcribe your speech using Whisper
   - Extract audio features (pitch, tone, pauses, etc.)
   - Generate a psychological assessment report
   - Retrieve relevant context from the vector DB
   - Generate an empathetic response
   - Convert response to speech
3. **View results**: See transcription, response text, and listen to audio reply
4. **Check conversation log** in the sidebar

### Review and Modify Responses

If you need to review or modify the therapeutic responses:

streamlit run review.py

Use this to:
- Review past interactions
- Modify responses if necessary
- Update the conversation database