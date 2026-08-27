# macOS Real-Time Translation & Voiceover Desktop

A real-time audio translation and voiceover desktop application for macOS built with **Tauri 2.0**, **React 18 (TypeScript + Tailwind CSS)**, **Python 3.11+**, and **Gemini 3.5 Live Translate (`gemini-3.5-live-translate-preview`)**.

---

## Features
- **Bidirectional Streaming Translation**: Real-time speech-to-speech translation using the Gemini Live API over WebSockets.
- **Sidechain Audio Ducking**: Dynamically attenuates original background / system audio while the translated voiceover is playing.
- **macOS System Audio Capture**: Seamless integration with microphone input or [BlackHole 2ch](https://github.com/ExistentialAudio/BlackHole) virtual audio cable.
- **Live Telemetry & Transcripts**: High-frequency (20 FPS) WebSocket updates for audio VU meters, ducking indicators, and synchronized live transcripts.

---

## Architecture Overview

```text
myProject/
├── src-tauri/                 # Native macOS window & Tauri 2.0 configuration
├── src/                       # React 18 frontend with TypeScript & Tailwind CSS
├── backend/                   # Python FastAPI sidecar (audio routing & Gemini Live stream)
│   ├── audio_engine.py        # PyAudio DSP, buffer mixing, sidechain ducking
│   ├── ai_pipeline.py         # Bidirectional Gemini 3.5 Live streaming
│   ├── main.py                # FastAPI HTTP + WebSocket endpoints
│   ├── requirements.txt       # Python dependencies
│   └── .env                   # Configuration (GEMINI_API_KEY)
└── package.json               # Node.js dependencies & scripts
```

---

## Prerequisites (macOS)

1. **PortAudio** (required for `pyaudio`):
   ```bash
   brew install portaudio
   ```
2. **Node.js** (v18+) & **npm**
3. **Python** (3.11+)
4. **Rust & Cargo** (for Tauri native desktop builds):
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   ```
5. *(Optional)* **BlackHole 2ch Virtual Audio Driver** (to capture system/app audio directly):
   ```bash
   brew install blackhole-2ch
   ```

---

## Quick Start / Development Setup

### 1. Configure Environment Variables
Create or edit `backend/.env`:
```bash
cp backend/.env.example backend/.env
```
Open `backend/.env` and add your Gemini API Key:
```env
GEMINI_API_KEY=your_actual_gemini_api_key
```

---

### 2. Run Python Backend Daemon

In your first terminal window:
```bash
# Navigate to backend directory
cd backend

# Create and activate Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the FastAPI server on port 8000
python main.py
```
> The backend will be available at `http://127.0.0.1:8000` with WebSocket telemetry at `ws://127.0.0.1:8000/ws`.

---

### 3. Run Frontend / Tauri Application

In a second terminal window (at project root):
```bash
# Install Node dependencies
npm install

# Option A: Run in Browser Mode (Fast UI Iteration)
npm run dev
# Open http://localhost:1420

# Option B: Run as Native macOS Desktop Window (Tauri)
npm run tauri dev
```

---

## Audio Ducking & Routing Guide

1. **Capture System Audio**: In macOS *System Settings > Sound*, or inside apps (Zoom, Discord, Chrome), set output to **BlackHole 2ch**.
2. **Configure App**:
   - **Input Device**: Select `BlackHole 2ch` (or your Microphone).
   - **Output Device**: Select your Speakers or Headphones.
   - **Ducking Level**: Adjust the slider (e.g. `20%`) to set background volume while translation is active.
   - **Target Language**: Choose target translation language.
   - Click **Start Gemini Live Translate**.
