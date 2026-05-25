# Sensia — Project Understanding & Quick Start Guide

## What Is This Project?

**Sensia** is a voice-based AI therapy assistant built with Python and Streamlit. A user uploads a recorded audio message, and the system:

1. Transcribes the speech using Whisper
2. Extracts acoustic/psychological features from the audio signal
3. Generates a clinical psychological assessment report using GPT-4
4. Retrieves relevant therapeutic context from a local vector database
5. Produces an empathetic, professional therapy response using GPT-4
6. Converts that response back to spoken audio using Microsoft Edge TTS
7. Logs every interaction for later review and database enrichment

---

## Project at a Glance

```
d:\Sensia\
├── AI_Therapist.py       ← Main app (run this for the therapist UI)
├── Audio_Analysis.py     ← Audio feature extraction + clinical report generation
├── create_db.py          ← One-time setup: build the vector database
├── review.py             ← Human-in-the-loop: review and improve AI responses
├── data.jsonl            ← Therapy Q&A training dataset (large JSON array)
├── requirements.txt      ← Python dependencies
├── readme.md             ← Original setup guide
│
│   (created at runtime)
├── New_DB/               ← ChromaDB vector store (created by create_db.py)
├── conversation_log.txt  ← Append-only log of all interactions (JSON lines)
└── output_edge.mp3       ← TTS audio output (overwritten each session)
```

---

## Technology Stack

| Layer | Tool / Library |
|---|---|
| UI framework | Streamlit |
| LLM | OpenAI GPT-4 via `langchain-openai` |
| Embeddings | OpenAI Embeddings via `langchain-openai` |
| Vector store | ChromaDB via `langchain-chroma` |
| Speech-to-text | `faster-whisper` (Whisper `base` model, CPU) |
| Text-to-speech | `edge-tts` (voice: `en-US-JennyNeural`) |
| Audio analysis | `librosa`, `numpy`, `scipy` |
| LLM orchestration | `langchain`, `langchain-core`, `langchain-community` |
| Config / secrets | `python-dotenv` |
| Async support | `nest-asyncio` (for edge-tts inside Streamlit) |

**Python version required:** 3.11+

---

## Architecture & Data Flow

```
User uploads WAV/MP3
        │
        ▼
┌─────────────────────────────────┐
│  1. Transcription               │
│     faster-whisper (base, CPU)  │
│     → plain text string         │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  2. Audio Feature Extraction    │
│     librosa + scipy             │
│     → dict of ~15 features      │
│       (pitch, energy, silence,  │
│        tempo, MFCCs, shimmer…)  │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  3. Psychological Assessment    │
│     GPT-4 (via LangChain chain) │
│     → clinical report text      │
│       (5-section structured MD) │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  4. RAG Retrieval               │
│     ChromaDB (New_DB/)          │
│     k=3 nearest chunks          │
│     → relevant therapy passages │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  5. Therapist Response          │
│     GPT-4 + custom prompt       │
│     Inputs combined:            │
│       • psych report (hidden)   │
│       • retrieved context       │
│       • conversation history    │
│       • user transcription      │
│     → empathetic reply text     │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│  6. Logging + TTS               │
│     conversation_log.txt        │
│     edge-tts → output_edge.mp3  │
└────────────────┬────────────────┘
                 │
                 ▼
        Displayed in browser
   (transcription + text + audio)
```

---

## File-by-File Breakdown

### `AI_Therapist.py` — Main Streamlit App

**Entry point.** Run with `streamlit run AI_Therapist.py`.

Key pieces:

- **`load_existing_vector_db()`** — Opens the persisted ChromaDB from `New_DB/` using OpenAI embeddings.
- **`transcribe_audio()`** — Loads `WhisperModel("base", device="cpu")` and transcribes an audio file path to text.
- **`text_to_speech_edge()`** — Wraps the async `edge_tts.Communicate` call using `nest_asyncio` so it works inside Streamlit's event loop.
- **`ask_question_with_audio_context()`** — Core response generation. Combines the psychological report, 3 retrieved RAG documents, conversation history, and the transcription into a single prompt for GPT-4.
- **`log_interaction()`** — Appends `{id, user_input, gpt_response}` as a JSON line to `conversation_log.txt`.
- **`custom_prompt`** — A `PromptTemplate` defining the therapist's behavior rules (greeting handling, name usage, boundary respect, professional tone).
- **Sidebar** — Reads and displays the last 10 log entries. Has a "Clear Log" button.
- **`chat_history`** — Stored in `st.session_state` so it survives Streamlit reruns within the same browser session.

Imports from `Audio_Analysis.py`: `extract_audio_features`, `display_audio_features`, `analyze_with_openai`, `AudioReportGenerator`.

---

### `Audio_Analysis.py` — Audio Feature Extraction & Clinical Report

**Helper module**, imported by `AI_Therapist.py`.

**`extract_audio_features(audio_data, sample_rate) → dict`**

Extracts ~15 numeric features from raw audio using `librosa`:

| Feature | What it captures |
|---|---|
| `rms_energy` | Volume / loudness |
| `pitch_mean`, `pitch_std` | Average pitch and its variability |
| `zero_crossing_rate` | Speech rate proxy |
| `spectral_centroid_mean` | Tone brightness |
| `spectral_contrast_mean` | Voice expressiveness |
| `spectral_bandwidth` | Articulation clarity |
| `spectral_rolloff` | Sound sharpness |
| `mfcc_mean`, `mfcc_std` | 13-coefficient voice quality vectors |
| `tempo` | Rhythm / speaking tempo in BPM |
| `silence_ratio` | Proportion of silence |
| `shimmer` | Amplitude irregularity |
| `energy_variance` | Speech monotony indicator |
| `speaking_rate` | Syllable-like energy peaks per second |

**`AudioReportGenerator` class**

Takes a transcription string and feature dict, builds a detailed clinical prompt, and runs it through GPT-4 (`temperature=0.3`) using `LLMChain`. The report has 5 sections: Speech Characteristics, Linguistic Features, Nonverbal Cues, Emotional Indicators, Conclusion.

**`analyze_with_openai(transcription, features) → str`**

Convenience wrapper: creates an `AudioReportGenerator` and returns the report string.

> Note: This file uses older-style LangChain imports (`langchain.chat_models`, `langchain.chains`, `langchain.prompts`) rather than the newer `langchain_openai` / `langchain_core` packages used in `AI_Therapist.py`. Both work but reflect a partial migration.

---

### `create_db.py` — Vector Database Builder

**One-time setup tool.** Run once (before using the main app) with `streamlit run create_db.py`.

**What it does:**

1. Accepts an uploaded `.jsonl` file via Streamlit.
2. Parses it as either a JSON array or true JSONL (one object per line).
3. Expects each record to have `instruction`, `input`, and `output` fields.
4. Combines them into: `"Instruction: …\nInput: …\nOutput: …"`
5. Splits all texts using `TokenTextSplitter(chunk_size=500, chunk_overlap=50)`.
6. Embeds and stores in ChromaDB at `New_DB/` in batches of 5,000 records.
7. Calls `vectordb.persist()` to save to disk.

The included `data.jsonl` is a large therapy Q&A dataset that feeds this database.

> Note: Uses older-style LangChain imports (`langchain.vectorstores.Chroma`, `langchain.embeddings.OpenAIEmbeddings`, `langchain.text_splitter`).

---

### `review.py` — Human-in-the-Loop Review UI

**Optional quality-improvement tool.** Run with `streamlit run review.py`.

**What it does:**

1. Reads every entry from `conversation_log.txt`.
2. Displays each user question and the original GPT response.
3. Shows a text area per entry where a human can type a revised/corrected answer (or leave blank to accept the original).
4. On "Save All to Vector DB", stores each entry as a `langchain.schema.Document` into the existing ChromaDB with metadata:
   - `source: "user_revision"` if a revision was entered
   - `source: "gpt_auto_approved"` if left blank

This creates a feedback loop: corrected or accepted responses are fed back into the vector database, improving future RAG retrieval quality.

> Note: `st.title()` is called before `st.set_page_config()` (lines 61 and 64), which may produce a Streamlit warning in some versions.

---

### `data.jsonl` — Training Dataset

A large therapy Q&A dataset stored as a JSON array. Each record has:

```json
{
  "instruction": "...",
  "input": "...",
  "output": "..."
}
```

This is the source data for the ChromaDB vector store. It is processed by `create_db.py`.

---

## Quick Start (Step-by-Step)

### Prerequisites

- Python 3.11 or higher
- An OpenAI API key with GPT-4 access

### Step 1 — Install dependencies

```powershell
cd d:\Sensia
pip install -r requirements.txt
```

> If you encounter issues with `faster-whisper`, you may need `pip install faster-whisper` separately and ensure you have the C++ redistributable installed on Windows.

### Step 2 — Create your `.env` file

Create a file named `.env` in `d:\Sensia\` with:

```
OPENAI_API_KEY=your_openai_api_key_here
```

### Step 3 — Build the vector database (one-time)

```powershell
streamlit run create_db.py
```

1. Open the browser URL shown (usually `http://localhost:8501`).
2. Upload `data.jsonl`.
3. Click **"Create Chroma Vector DB"**.
4. Wait — this processes a large file and makes many OpenAI embedding API calls. It can take several minutes.
5. A `New_DB/` folder will be created when done.

### Step 4 — Run the AI Therapist

```powershell
streamlit run AI_Therapist.py
```

1. Open the browser URL.
2. Upload a WAV or MP3 audio file.
3. The system will transcribe, analyze, and respond automatically.
4. Listen to the audio response and read the text reply.
5. Check the sidebar for the conversation log.

### Step 5 — (Optional) Review past interactions

```powershell
streamlit run review.py
```

Use this to review logged interactions, correct any poor GPT responses, and save improved answers back to the vector database.

---

## Key Design Decisions

### Why RAG?
The system uses Retrieval-Augmented Generation so GPT-4 can draw on a large body of therapy-specific Q&A when forming responses, rather than relying solely on its training data. This grounds responses in domain-specific therapeutic language.

### Why audio features + a psychological report?
Rather than sending raw audio metrics directly to GPT-4, the system first generates a structured clinical report from those metrics. GPT-4 then reads this report as hidden background context — it informs the tone and empathy of the reply without being recited to the user.

### Why conversation history in session state?
Streamlit re-runs the entire script on each user interaction. `st.session_state` is used to carry `chat_history` across reruns within the same browser session, giving the therapist conversational continuity within a session.

### Why `nest_asyncio`?
`edge-tts` uses `async/await`. Streamlit runs its own event loop. `nest_asyncio.apply()` patches the running loop to allow nested async calls, avoiding the "event loop already running" error.

---

## Known Issues & Gotchas

| Issue | Location | Detail |
|---|---|---|
| Mixed LangChain imports | `Audio_Analysis.py`, `create_db.py`, `review.py` | These files use `langchain.*` (v0.1-style). `AI_Therapist.py` uses `langchain_openai`, `langchain_chroma`, `langchain_core` (v0.2+ style). May cause deprecation warnings. |
| `st.set_page_config` order | `review.py` line 64 | Called after `st.title()` on line 61; Streamlit requires `set_page_config` to be the first Streamlit command. May print a warning. |
| `review.py` no file guard | `review.py` `load_conversation()` | Will crash if `conversation_log.txt` does not yet exist. Run the main therapist first. |
| Whisper model reload | `AI_Therapist.py` `transcribe_audio()` | `WhisperModel` is re-instantiated on every audio upload. This is slow. Caching with `@st.cache_resource` would speed it up. |
| Older Chroma `.persist()` | `create_db.py` | `vectordb.persist()` is deprecated in newer ChromaDB versions. May show a deprecation warning but still works. |
| Large `data.jsonl` | Root directory | File is stored as a single JSON array, not true JSONL. The `load_jsonl_text()` function handles both formats. |

---

## Environment Variables Reference

| Variable | Required | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | Yes | Used by all OpenAI calls (GPT-4 completions + embeddings) |

---

## API / External Services Used

| Service | How it's used | Cost implication |
|---|---|---|
| OpenAI GPT-4 | Clinical report generation + therapy responses | Per-token billing (GPT-4 is expensive) |
| OpenAI Embeddings | Vectorizing therapy dataset + query retrieval | Per-token billing (cheaper than GPT-4) |
| Microsoft Edge TTS | Converting therapist text reply to audio | Free (no API key needed, uses edge-tts library) |

---

## File Relationships Diagram

```
data.jsonl
    │
    ▼ (create_db.py — one-time setup)
New_DB/  ◄──────────────────────────────────────────┐
    │                                                │
    │ (AI_Therapist.py — main loop)                  │
    ├── RAG retrieval (k=3)                          │
    │                                                │
Audio_Analysis.py                                    │
    ├── extract_audio_features()                     │
    └── analyze_with_openai()                        │
            │                                        │
            ▼                                        │
    AI_Therapist.py                                  │
            │                                        │
            ├── transcribe_audio()                   │
            ├── ask_question_with_audio_context()    │
            ├── log_interaction() ──► conversation_log.txt
            └── text_to_speech_edge() ──► output_edge.mp3
                                             │
                                  (review.py — optional)
                                  Reviews conversation_log.txt
                                  Saves corrections back to New_DB/ ─┘
```
