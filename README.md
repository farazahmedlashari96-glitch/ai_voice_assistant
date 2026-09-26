# 📘 AI Voice Assistant using Speech-to-Text, LLM API, and Text-to-Speech

## 🧩 Project Domain / Category
Artificial Intelligence / Natural Language Processing / Speech Processing / Web Application

## 📄 Abstract / Introduction
An AI-powered voice assistant that **listens** to the user through the microphone, converts the speech into
text (**STT**), sends the text to a **Large Language Model** through an API, and converts the reply back into
speech (**TTS**) — a complete conversational loop without typing.

Everything AI-related runs through **one Groq API key**. All assistant logic is **Python (Django)**. You can use it
in the **terminal** (`python manage.py talk`) or in the **React web app** — the brief allows a CLI or a web interface. The code is split into small modules (`stt`, `llm`, `tts`, `text_processing`, `audio_store`,
`pipeline`) to show API integration, speech processing and modular system design.

## 🎯 Objectives

| Objective | Where |
|---|---|
| Build a voice-based AI assistant | the whole app: `backend/` + `frontend/` |
| Integrate Speech-to-Text for voice input | `backend/assistant/services/stt.py` (Groq Whisper) |
| Use an LLM API for intelligent responses | `backend/assistant/services/llm.py` (Groq Llama) |
| Convert generated text into speech | `backend/assistant/services/tts.py` (Groq Orpheus) |
| User-friendly interface | `frontend/` (React) |

## 🔬 Project Workflow

```
1 Capture voice input ─► 2 Speech → text (STT) ─► 3 Text → LLM API ─► 4 Receive response
                                                                            │
                         6 Output audio + display text ◄─ 5 Response → speech (TTS)
```

| Step | Implementation |
|---|---|
| 1. Capture voice input | Terminal: `services/recorder.py` (Python). Web: `frontend/src/hooks/useRecorder.js`. Both record a 16 kHz mono **WAV** |
| 2. Speech → text | `POST /api/voice/` → `stt.py` (`whisper-large-v3-turbo`) |
| 3. Text → LLM API | `pipeline.py` → `llm.py` (`llama-3.3-70b-versatile`, fallback `llama-3.1-8b-instant`) |
| 4. Receive response | reply text + timings returned as JSON |
| 5. Response → speech | `tts.py` (`canopylabs/orpheus-v1-english`) |
| 6. Output audio + text | Terminal: `services/player.py` plays it and the text is printed. Web: `Message.jsx` shows the text, an audio player (auto-plays) and the response time |

## ⚙️ Functional Requirements

| # | Requirement | How it is met |
|---|---|---|
| 1 | **Audio input** — microphone, WAV recommended | Python: `recorder.py` (`sounddevice` → WAV). Web: browser microphone → WAV (`useRecorder.js`, `audio/wav.js`) |
| 2 | **STT** — short sentences, basic noise & pauses | Adaptive noise threshold + auto-stop on a pause (`recorder.py` and browser); Whisper's own no-speech filter drops noise-only "transcripts" (server) |
| 3 | **LLM API integration** — authentication, request/response | `groq_client.py` (key from environment, timeout, retries), `llm.py` (fallback model, friendly errors) |
| 4 | **Text processing** — clean text, system prompt | `text_processing.py` cleans input; `SYSTEM_PROMPT` in `config/settings.py` |
| 5 | **TTS** — speech, playback, clarity | `tts.py` splits replies into sentence chunks (Groq's 200-character limit), joins them into one WAV; played automatically (`player.py` / browser). If Groq's voice fails, the terminal prints the text and the browser's voice reads it |
| 6 | **Conversation flow** — loop, exit command | The loop re-opens the mic after every reply (terminal: `talk.py`; web: *Continuous conversation*). Say or type **exit / stop / quit / goodbye / bye** to end |
| 7 | **User interface** — user text, AI text, audio playback | CLI: `python manage.py talk`. Web: React page with your words, the AI's words and an audio player per reply |
| 8 | **Error handling** — unclear audio, API fails, no input | `no_input`, `unclear_audio`, blocked microphone, API down / rate limit / bad key / timeout, TTS failure — each shows a clear message and the app keeps running |

## 🧠 Non-Functional Requirements

| Requirement | How it is met |
|---|---|
| Respond within 2–5 seconds | Fast Groq models, parallel TTS chunks, short replies (system prompt + `LLM_MAX_TOKENS`). Every reply shows its response time (green ≤ 5 s) and `python manage.py evaluate` measures it — **measure it on your own connection** |
| Modular, well-structured code | Services layer separate from views and UI; small single-purpose files; unit-tested |
| API keys stored securely | Only in `backend/.env` (git-ignored); never sent to the browser |
| Easy to run and test | 3 commands to run; `python manage.py test` and `npm test` need no key or network |

## 🛠️ Tools & Technologies
* **Language:** Python — recording, STT, LLM, TTS, playback and the terminal app are all Python. The optional browser page is React/JavaScript
* **Environment:** VS Code / PyCharm (any editor)
* **Libraries:** `groq` SDK (STT, LLM and TTS calls, API handling) · `django` · `django-cors-headers` · `python-dotenv` · React + Vite

## 📚 Prerequisites
Basic Python · understanding of APIs and HTTP requests · basic AI/NLP concepts · audio processing (optional).
You need **Python 3.10+**, **Node 18+** and a Groq API key.

## 🧪 Implementation Steps (Phases)

| Phase | What to do / where |
|---|---|
| **1. Research & Setup** | Read the *Workflow* above. Setup: see **Run it** below |
| **2. Audio Processing** | Recording: `recorder.py` (Python) and `useRecorder.js` (web). Store & manage files: `audio_store.py` saves every recording and reply to `backend/audio_files/{recordings,responses}/` with timestamped names and keeps the newest 20 (`KEEP_LAST_FILES`) |
| **3. STT Integration** | `stt.py`. Test accuracy with different inputs: put WAV files in `backend/evaluation/samples/` (see its README) and run `evaluate` |
| **4. LLM API Integration** | Register at <https://console.groq.com/keys>, put the key in `backend/.env`. Send/handle requests in `llm.py`. Optimise prompts by editing `SYSTEM_PROMPT` and comparing replies with `evaluate` |
| **5. TTS Integration** | `tts.py`; smooth playback in `useSpeaker.js` and the player under each reply |
| **6. System Integration** | `pipeline.py` connects STT + LLM + TTS; the loop lives in `talk.py` (terminal) and `frontend/src/App.jsx` (web) |
| **7. UI Development** | Terminal output in `talk.py`; web UI in `frontend/src/components/` |
| **8. Testing & Evaluation** | `python manage.py test`, `npm test`, and `python manage.py evaluate` (accuracy + speed report) |

## 📊 Evaluation Criteria — how each is measured

| Criterion | How |
|---|---|
| Accuracy of speech recognition | `evaluate` computes the **Word Error Rate** for each sample WAV that has a matching `.txt` |
| Quality of AI-generated responses | `evaluate` runs the questions in `evaluation/prompts.txt` and writes `evaluation/report.csv` with an empty `quality_score` column to rate replies 1–5 |
| Smoothness of speech output | Listen through the player; replies are stitched into one continuous WAV |
| System response time | Shown under every reply (STT / LLM / TTS breakdown on hover) and averaged by `evaluate` against the 5 s target |
| Code structure and modularity | Layered services, tests: 67 backend + 19 frontend |
| User interface usability | One main button, live status, level meter, clear error messages |

Example: `python manage.py evaluate` prints per-case timings and a summary such as
`Speech recognition: average WER 0.050 …`, `Within the 5s response-time target: 9/10`.

## 🚀 Optional Enhancements (Bonus)

| Enhancement | Status |
|---|---|
| Memory for conversation context | ✅ Done — the last 12 messages are sent with every request |
| Web app | ✅ Done — Django + React (instead of Streamlit/Flask) |
| Wake word ("Hey Assistant") | ❌ Not included |
| Real-time streaming | ❌ Not included (latency is reduced with fast models and parallel TTS instead) |
| External services (weather, WhatsApp…) | ❌ Not included |

## Project structure

```
ai_voice_assistant/
├── backend/                         # Django (Python)
│   ├── manage.py, requirements.txt, .env.example
│   ├── config/                      # settings, urls
│   ├── audio_files/                 # stored recordings/ and responses/  (Phase 2)
│   ├── evaluation/                  # samples/, prompts.txt  (Phase 8)
│   └── assistant/
│       ├── views.py, urls.py        # /api/voice/  /api/chat/  /api/health/
│       ├── metrics.py               # Word Error Rate
│       ├── management/commands/talk.py       # terminal voice assistant (Python)
│       ├── management/commands/evaluate.py   # accuracy + speed report
│       ├── services/
│       │   ├── groq_client.py       # shared client + friendly errors
│       │   ├── recorder.py  player.py   # microphone → WAV, speakers (terminal mode)
│       │   ├── stt.py  llm.py  tts.py
│       │   ├── text_processing.py   # cleaning, exit commands, TTS splitting
│       │   ├── audio_store.py       # store / prune audio files
│       │   ├── pipeline.py          # one conversation turn
│       │   └── errors.py
│       └── tests/
└── frontend/                        # React + Vite
    ├── public/recorder-worklet.js   # microphone capture (audio thread)
    └── src/
        ├── App.jsx                  # conversation loop: idle → listening → thinking → speaking
        ├── api.js
        ├── audio/wav.js, base64.js  # WAV encoding, 16 kHz resampling
        ├── hooks/useRecorder.js, useSpeaker.js
        ├── components/ChatLog, Message, Controls
        └── *.test.js(x)
```

## Run it (Phase 1 — setup)

```bash
# 1) Backend
cd backend
python -m venv venv
source venv/bin/activate              # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                  # Windows: copy .env.example .env  -> then set GROQ_API_KEY
python manage.py runserver            # http://127.0.0.1:8000   (no database, nothing to migrate)

# 2a) Web app — frontend (second terminal)
cd frontend
npm install
npm run dev                           # open http://localhost:5173  and allow the microphone

# 2b) OR terminal mode, Python only (no Node needed)
python manage.py talk                 # speak into the microphone; say "exit" or "stop" to quit
python manage.py talk --text          # type instead of speaking (no microphone needed)
```

Terminal mode needs `sounddevice` (in `requirements.txt`); on Linux also `sudo apt install libportaudio2`.
Find your microphone with `python manage.py talk --list-devices`.

In the web app press **Start talking**, ask something, and pause. With *Continuous conversation* on, the assistant keeps
listening after every reply until you say **"exit"** or **"stop"** (or press **Stop**). You can also type a message —
useful for testing without a microphone.

## API

Responses are JSON; errors look like `{"error": {"code": "...", "message": "..."}}`.

| Endpoint | Purpose |
|---|---|
| `GET /api/health/` | status, whether the key is set, models, response-time target |
| `POST /api/voice/` | multipart: `audio` (WAV), `history` (JSON list), `speak` → `transcript`, `user_text`, `reply`, `exit`, `audio` (base64 WAV), `timings` |
| `POST /api/chat/` | JSON: `message`, `history`, `speak` → same, without `transcript` |

Error codes: `no_input`, `unclear_audio` (422) · `audio_too_large` (413) · `config_error` (503) · `auth_error`,
`model_unavailable`, `upstream_error` (502) · `rate_limited` (429) · `upstream_unavailable` (503) · `upstream_timeout` (504).

## Configuration (`backend/.env`)

| Variable | Default | Notes |
|---|---|---|
| `GROQ_API_KEY` | — | **Required** — the only key needed |
| `GROQ_LLM_MODEL` / `GROQ_LLM_FALLBACK_MODEL` | `llama-3.3-70b-versatile` / `llama-3.1-8b-instant` | Fallback is used if the first is unavailable or rate-limited |
| `GROQ_STT_MODEL` | `whisper-large-v3-turbo` | |
| `GROQ_TTS_MODEL` / `GROQ_TTS_VOICE` | `canopylabs/orpheus-v1-english` / `autumn` | voices: autumn, diana, hannah, austin, daniel, troy |
| `STT_LANGUAGE` | *(auto)* | e.g. `en`, `ur`, `es` to force the spoken language |
| `LLM_MAX_TOKENS` | `300` | lower = faster, shorter replies |
| `MAX_HISTORY_MESSAGES` | `12` | conversation memory sent to the LLM |
| `STORE_AUDIO` / `KEEP_LAST_FILES` | `True` / `20` | set `STORE_AUDIO=False` to stop saving recordings |
| `MIC_SILENCE_SECONDS` / `MIC_NO_SPEECH_SECONDS` / `MIC_DEVICE` | `1.4` / `8` / *(default mic)* | terminal-mode microphone tuning |

Model names and availability change; check <https://console.groq.com/docs/models> if one is reported unavailable.

## Notes & troubleshooting
* **Microphone** — in the browser you must allow access (works on `localhost` or HTTPS only). In terminal mode use `--list-devices` / `MIC_DEVICE` if the wrong microphone is used; if it never detects your voice, speak closer or lower `MIC_SILENCE_SECONDS`.
* **Privacy** — recordings are sent to Groq for transcription and (by default) also saved in `backend/audio_files/`.
* **Voice limits** — Groq's Orpheus voice takes 200 characters per request and speaks English or Saudi Arabic. Only the first ~600 characters of a very long reply are spoken; the text is always complete. Speech recognition understands many languages (`STT_LANGUAGE`).
* **`model_unavailable`** — check the model name in `.env` and your project's *Model Permissions* in the Groq console.
* **Rate limited (429)** — free tiers have per-minute limits; wait a moment (the fallback model helps).
* **Security** — the API has no login; add authentication before exposing it publicly. `runserver` is for development; for production use gunicorn/uvicorn, `npm run build`, `DJANGO_DEBUG=False`, a real `DJANGO_SECRET_KEY`, and `VITE_API_BASE` if the API is on another domain.
