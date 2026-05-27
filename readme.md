# Sensia — Voice & Text Therapy Companion (POC)

Sensia is a mental-health support POC with a **React UI** (`sensia_ui-main`) and **FastAPI** backend (`api_server.py`). It combines speech analysis, Whisper transcription, RAG (Chroma + HuggingFace embeddings), **Groq** chat, optional **Redis** session memory, **input guardrails**, and Edge TTS.

> **Legacy:** `AI_Therapist.py` and Streamlit flows are deprecated. Use `run_backend.ps1` + `run_ui.ps1` for day-to-day development.

## Features

- **Multi-modal input:** typed chat, microphone (MediaRecorder), or audio upload (WAV/MP3/M4A)
- **Speech pipeline:** faster-whisper transcription; upload path adds librosa features + Groq clinical-style report (`Audio_Analysis.py`)
- **RAG-grounded replies:** Chroma vector DB (`New_DB/`) with therapy context
- **Session memory:** Redis turns + rolling 5-turn LLM summaries (in-memory fallback if Redis is down)
- **Input guardrails:** off-topic refusal, crisis helplines (region-specific), harmful content — via `sensia_guardrails.py` + `guardrails_policy.json`
- **TTS:** on-demand Edge TTS (`POST /api/.../tts`) with a single audio player in the UI (no overlapping playback)
- **Optional logging:** `conversation_log.txt` (not required for the React UI path)

## Requirements

- **Python 3.11+** with project venv (`venv/`)
- **Node.js 20+** (for `sensia_ui-main`)
- **Groq API key** in `.env` — see [`.env.example`](.env.example)
- **Redis** (optional): `REDIS_URL` or `REDIS_HOST` / `REDIS_PORT` / etc. in `.env`
- First run downloads the HuggingFace embedding model (`sentence-transformers/all-mpnet-base-v2`)

### Redis locally (Docker)

```bash
docker run -d --name sensia-redis -p 6379:6379 redis:7-alpine
```

Then set `REDIS_URL=redis://localhost:6379/0` in `.env`.

## Quick start

### 1. Python dependencies

```powershell
cd D:\Sensia
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Environment variables

**Do not commit `.env` to git** — it is listed in [`.gitignore`](.gitignore).

```powershell
Copy-Item .env.example .env
# Edit .env and set GROQ_API_KEY (and Redis if used)
```

| Variable | Required | Notes |
|----------|----------|--------|
| `GROQ_API_KEY` | Yes | Groq chat completions |
| `GROQ_MODEL` | No | Default `llama-3.3-70b-versatile` |
| `REDIS_URL` / `REDIS_*` | No | Persistent sessions; memory fallback |
| `SENSIA_GUARDRAILS_ENABLED` | No | Default `1` (on) |
| `SENSIA_CRISIS_REGION` | No | `IN` (default), `US`, or `UK` |

Tune guardrail phrases in [`guardrails_policy.json`](guardrails_policy.json). Set `SENSIA_GUARDRAILS_ENABLED=0` to disable the input gate (prompt scope rules still apply).

### 3. Vector database (first time only)

Ingest training data into Chroma **before** chatting (still uses Streamlit UI for this step):

```powershell
.\venv\Scripts\streamlit run create_db.py
```

1. Upload `data.jsonl` (or your JSON/JSONL training file)
2. Click **Create Chroma Vector DB**
3. Output is saved under `New_DB/` (gitignored)

### 4. Run the app (two terminals)

**Terminal 1 — API** (http://127.0.0.1:8000):

```powershell
.\run_backend.ps1
```

**Terminal 2 — UI** (Vite dev server, typically http://localhost:5173):

```powershell
.\run_ui.ps1
```

Open the URL shown in the Vite terminal (not a `file://` preview). The UI proxies `/api` → `http://127.0.0.1:8000`.

**Health check:** http://127.0.0.1:8000/api/health

### Manual start (optional)

```powershell
.\venv\Scripts\python.exe -m uvicorn api_server:app --host 127.0.0.1 --port 8000 --reload
cd sensia_ui-main
npm install
npm run dev
```

## Using the React UI

- **New session** — created automatically; session list stored in browser `localStorage`
- **Chat** — type a message and send (`POST /api/sessions/{id}/chat`)
- **Mic** — record a voice note (`POST .../mic`); Whisper → `ask_question`
- **Upload** — full audio analysis path (`POST .../audio/analyze`)
- **TTS** — play/pause assistant reply; one shared `<audio>` element
- **Guardrails** — off-topic or crisis messages return a canned reply (no main LLM); UI may show a toast when `guardrail_triggered` is true

Example off-topic test: *"Who is the prime minister?"* → short refusal, no factual answer.

## API overview

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Redis / backend status |
| POST | `/api/sessions` | New session ID |
| GET | `/api/sessions/{id}/turns` | Conversation history |
| POST | `/api/sessions/{id}/chat` | Text message |
| POST | `/api/sessions/{id}/mic` | Voice note (multipart) |
| POST | `/api/sessions/{id}/audio/analyze` | Upload + analysis |
| POST | `/api/sessions/{id}/tts` | Edge TTS MP3 |
| DELETE | `/api/sessions/{id}` | Clear session data |

Chat/mic/analyze responses include optional `guardrail_triggered` and `guardrail_category`.

## Tests

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_guardrails.py -q
```

## Architecture

- **[`Doc/architecture.md`](Doc/architecture.md)** — full system architecture (modules, flows, API, data, security, file review)
- [`Doc/Sensia-Workflow.png`](Doc/Sensia-Workflow.png) — **workflow** from user input → API → guardrails → response (demo-friendly)
- [`Doc/Sensia-HLD.png`](Doc/Sensia-HLD.png) — HLD diagram image (from `architecture.md`)
- Diagrams (Draw.io / [diagrams.net](https://app.diagrams.net)):
  - [`Doc/Sensia-HLD.drawio`](Doc/Sensia-HLD.drawio) — editable HLD source
  - [`Doc/Sensia-LLD.drawio`](Doc/Sensia-LLD.drawio) — modules, API, sequences
  - [`Doc/Sensa flow diagam.drawio`](Doc/Sensa%20flow%20diagam.drawio) — vertical demo pipeline

Input is evaluated in `sensia_guardrails.evaluate_user_message()` before RAG/LLM inside `therapist_core.ask_question()`.

## Git & secrets

- Commit [`.env.example`](.env.example), not `.env`
- Root [`.gitignore`](.gitignore) excludes `.env`, `venv/`, `New_DB/`, logs, and `node_modules/`
- If `.env` was ever pushed, rotate API keys and run `git rm --cached .env`

## Legacy / optional tools

| Tool | Command | Notes |
|------|---------|--------|
| Vector DB builder | `streamlit run create_db.py` | One-time ingest |
| Response review | `streamlit run review.py` | Past log / DB review |
| Streamlit app | `AI_Therapist.py` | Prints migration notice only |

## Project layout (main)

```
Sensia/
├── api_server.py          # FastAPI entry
├── therapist_core.py      # ask_question, chat, mic, audio, TTS
├── sensia_guardrails.py   # Input guardrails
├── conversation_store.py  # Redis / in-memory turns & summaries
├── sensia_ui-main/        # React + Vite UI
├── run_backend.ps1
├── run_ui.ps1
├── .env.example           # Template (safe to commit)
└── tests/test_guardrails.py
```
