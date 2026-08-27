# Real-Time Translation and Voiceover App Design (Gemini 3.5 Live API)

## 1. Overview
A low-latency macOS desktop application that captures system or microphone audio, streams it to **Gemini 3.5 Live Translate (`gemini-3.5-live-translate-preview`)**, receives translated speech audio and transcriptions in real-time, and mixes it back with the original background audio using a sidechain ducking effect.

## 2. Architecture & Directory Structure
The system uses Tauri 2.0 as the native desktop wrapper, React/Vite for the frontend, and a lightweight Python FastAPI sidecar for audio I/O and the Gemini Live WebSocket session.

```text
myProject/
├── src-tauri/                 # Rust core and Tauri configuration
│   ├── tauri.conf.json        # Declares the Python sidecar binary
│   └── src/main.rs            # Rust entry point (minimal, spawns sidecar)
├── src/                       # React + Vite Frontend (TypeScript)
│   ├── App.tsx                # Main UI (Mic selector, target language, start/stop, ducking slider)
│   ├── api.ts                 # HTTP and WebSocket client to FastAPI
│   └── index.css              # Tailwind CSS imports
├── backend/                   # Python Backend (Lightweight Sidecar)
│   ├── main.py                # FastAPI server (Endpoints & WebSocket telemetry)
│   ├── audio_engine.py        # PyAudio streams, buffer handling, ducking math
│   ├── ai_pipeline.py         # Gemini 3.5 Live Translate bidirectional streaming (google-genai)
│   ├── requirements.txt       # Dependencies (fastapi, uvicorn, pyaudio, numpy, google-genai)
│   └── build_sidecar.sh       # Script to bundle Python into a standalone binary using PyInstaller
└── package.json               # Node dependencies for Tauri/Vite
```

## 3. Core Audio Pipeline
Implemented in `backend/audio_engine.py`.
- **Framework:** `PyAudio` running non-blocking async loops.
- **Ducking Mechanism:**
  - Uses `numpy` for buffer math.
  - While translated audio is playing, the original audio buffer is multiplied by `ducking_factor` (e.g., 0.2 for 20% volume).
  - The ducked original audio and the translated audio arrays are summed and clipped to $[-32768, 32767]$ for the output stream.

## 4. AI Pipeline (Gemini Live API)
Implemented in `backend/ai_pipeline.py`.
- **Model:** `gemini-3.5-live-translate-preview` via the official `google-genai` SDK.
- **Streaming Mode:**
  - Sends raw PCM input chunks (`16kHz, 16-bit, mono`).
  - Receives live translated audio PCM (`24kHz, 16-bit, mono`), automatically resampled to 16kHz for seamless mixing.
  - Receives simultaneous input (`input_transcription`) and output (`output_transcription`) text parts.
- **Interruption Handling:** Clears playback queues when Gemini detects interruption.

## 5. Frontend & IPC Bridge
- **IPC Protocol:** FastAPI serves HTTP commands (`POST /start`, `POST /stop`, `GET /devices`, `POST /ducking`) and a WebSocket connection (`WS /ws`) for real-time telemetry (dB level, ducking status, transcripts).
- **Frontend Framework:** React 18, Vite, Tailwind CSS, TypeScript.
- **UI Components:**
  - Audio device selectors (Microphone / BlackHole Virtual Audio Cable).
  - Target language selector (Ukrainian, English, Spanish, German, French, Polish, Japanese, Chinese).
  - Ducking level slider and VU audio level meter.
  - Live synchronized transcript view for source and target languages.
