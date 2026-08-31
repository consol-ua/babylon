import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Set, List, Dict
from dotenv import load_dotenv

# Load .env file from backend or root directory
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from audio_engine import DualChannelAudioEngine
from ai_pipeline import GeminiLiveAudioSession

@asynccontextmanager
async def lifespan(app: FastAPI):
    broadcast_task = asyncio.create_task(state_broadcast_loop())
    try:
        yield
    finally:
        broadcast_task.cancel()
        try:
            await broadcast_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Real-Time Call Translation & Voiceover Backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Audio Engine
audio_engine = DualChannelAudioEngine()

# Global AI Sessions
outgoing_ai = GeminiLiveAudioSession(
    api_key=os.environ.get("GEMINI_API_KEY", ""),
    target_lang="en",
    channel_name="outgoing",
)
incoming_ai = GeminiLiveAudioSession(
    api_key=os.environ.get("GEMINI_API_KEY", ""),
    target_lang="uk",
    channel_name="incoming",
)

# Request Models
class CallStartRequest(BaseModel):
    my_mic_index: Optional[int] = None
    call_virtual_mic_index: Optional[int] = None
    call_input_index: Optional[int] = None
    headphones_index: Optional[int] = None
    partner_lang: str = "en"
    ducking_factor: float = 0.2
    api_key: Optional[str] = None

class SampleStartRequest(BaseModel):
    sample_id: str
    headphones_index: Optional[int] = None
    ducking_factor: float = 0.2
    partner_lang: str = "en"
    api_key: Optional[str] = None

class DuckingRequest(BaseModel):
    ducking_factor: float

class AppState:
    def __init__(self) -> None:
        self.is_call_active: bool = False
        self.is_testing_active: bool = False
        self.active_sample_id: Optional[str] = None
        self.partner_lang: str = "en"

        # Outgoing (My Voice: UA -> Target)
        self.outgoing_stt: str = ""
        self.outgoing_translation: str = ""
        self.outgoing_volume_db: float = -100.0

        # Incoming (Call / Sample: Target -> UA)
        self.incoming_stt: str = ""
        self.incoming_translation: str = ""
        self.incoming_volume_db: float = -100.0
        self.is_incoming_ducking: bool = False

state = AppState()

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.active_connections.discard(connection)

manager = ConnectionManager()

# Hook up Telemetry Callbacks
def on_outgoing_telemetry(db: float) -> None:
    state.outgoing_volume_db = db

def on_incoming_telemetry(db: float, is_ducking: bool) -> None:
    state.incoming_volume_db = db
    state.is_incoming_ducking = is_ducking

audio_engine.outgoing_telemetry_cb = on_outgoing_telemetry
audio_engine.incoming_telemetry_cb = on_incoming_telemetry

# Hook up AI STT & Translation Callbacks
def on_out_stt(text: str, is_final: bool) -> None:
    state.outgoing_stt = text

def on_out_trans(text: str) -> None:
    state.outgoing_translation = text

def on_in_stt(text: str, is_final: bool) -> None:
    state.incoming_stt = text

def on_in_trans(text: str) -> None:
    state.incoming_translation = text

outgoing_ai.on_stt_result = on_out_stt
outgoing_ai.on_translated_result = on_out_trans

incoming_ai.on_stt_result = on_in_stt
incoming_ai.on_translated_result = on_in_trans

# 20 FPS Broadcast Loop
async def state_broadcast_loop() -> None:
    while True:
        if manager.active_connections:
            await manager.broadcast(
                {
                    "is_call_active": state.is_call_active,
                    "is_testing_active": state.is_testing_active,
                    "active_sample_id": state.active_sample_id,
                    "partner_lang": state.partner_lang,
                    "outgoing": {
                        "stt_text": state.outgoing_stt,
                        "translated_text": state.outgoing_translation,
                        "volume_db": round(state.outgoing_volume_db, 1),
                    },
                    "incoming": {
                        "stt_text": state.incoming_stt,
                        "translated_text": state.incoming_translation,
                        "volume_db": round(state.incoming_volume_db, 1),
                        "is_ducking": state.is_incoming_ducking,
                    },
                }
            )
        await asyncio.sleep(0.05)

# Built-in Samples Metadata
SAMPLES_DIR = Path(__file__).parent / "samples"
AVAILABLE_SAMPLES = [
    {
        "id": "it_standup",
        "title": "IT Daily Standup",
        "category": "IT & Team",
        "description": "Daily status report: backend microservices, DB queries optimization, WebSocket integration.",
        "filename": "it_standup.wav",
    },
    {
        "id": "tech_interview",
        "title": "System Architecture Interview",
        "category": "Job Interview",
        "description": "Technical question about high-load distributed streaming and geographic failover.",
        "filename": "tech_interview.wav",
    },
    {
        "id": "small_talk",
        "title": "Casual Small Talk",
        "category": "General Conversation",
        "description": "Friendly conversation about weekly activities, pleasant weather, and weekend plans.",
        "filename": "small_talk.wav",
    },
]

@app.get("/devices")
def get_devices():
    """List available audio input and output devices."""
    return {"devices": audio_engine.list_devices()}

@app.get("/samples")
def get_samples():
    """List built-in demo audio samples."""
    return {"samples": AVAILABLE_SAMPLES}

@app.post("/call/start")
async def start_call(req: CallStartRequest):
    """Start full-duplex bidirectional call translation."""
    if state.is_call_active or state.is_testing_active:
        return {"status": "already_running"}

    api_key = req.api_key or os.environ.get("GEMINI_API_KEY", "")
    outgoing_ai.set_api_key(api_key)
    incoming_ai.set_api_key(api_key)

    state.partner_lang = req.partner_lang
    outgoing_ai.target_lang = req.partner_lang
    incoming_ai.target_lang = "uk"

    audio_engine.set_ducking_factor(req.ducking_factor)

    state.outgoing_stt = ""
    state.outgoing_translation = ""
    state.incoming_stt = ""
    state.incoming_translation = ""

    audio_engine.start_call(
        my_mic_index=req.my_mic_index,
        call_virtual_mic_index=req.call_virtual_mic_index,
        call_input_index=req.call_input_index,
        headphones_index=req.headphones_index,
    )

    # Launch audio processing and AI stream workers
    asyncio.create_task(audio_engine.outgoing_process_loop())
    asyncio.create_task(audio_engine.incoming_process_loop())

    asyncio.create_task(
        outgoing_ai.run(audio_engine.outgoing_input_queue, audio_engine.outgoing_tts_queue)
    )
    asyncio.create_task(
        incoming_ai.run(audio_engine.incoming_input_queue, audio_engine.incoming_tts_queue)
    )

    state.is_call_active = True
    return {"status": "call_started"}

@app.post("/call/stop")
def stop_call():
    """Stop live call session."""
    audio_engine.stop_call()
    outgoing_ai.stop()
    incoming_ai.stop()
    state.is_call_active = False
    return {"status": "call_stopped"}

@app.post("/samples/start")
async def start_sample_test(req: SampleStartRequest):
    """Play built-in demo sample and run it through incoming translation pipeline."""
    if state.is_call_active or state.is_testing_active:
        return {"status": "already_running"}

    sample_meta = next((s for s in AVAILABLE_SAMPLES if s["id"] == req.sample_id), None)
    if not sample_meta:
        raise HTTPException(status_code=404, detail="Sample not found")

    sample_path = SAMPLES_DIR / sample_meta["filename"]
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail=f"Sample file {sample_meta['filename']} missing")

    api_key = req.api_key or os.environ.get("GEMINI_API_KEY", "")
    incoming_ai.set_api_key(api_key)
    incoming_ai.target_lang = "uk"
    state.partner_lang = req.partner_lang

    audio_engine.set_ducking_factor(req.ducking_factor)

    state.incoming_stt = ""
    state.incoming_translation = ""
    state.active_sample_id = req.sample_id
    state.is_testing_active = True

    audio_engine.start_sample_test(headphones_index=req.headphones_index)

    asyncio.create_task(
        incoming_ai.run(audio_engine.incoming_input_queue, audio_engine.incoming_tts_queue)
    )

    async def run_sample():
        try:
            await audio_engine.sample_playback_loop(str(sample_path))
        finally:
            incoming_ai.stop()
            audio_engine.stop_sample_test()
            state.is_testing_active = False
            state.active_sample_id = None

    asyncio.create_task(run_sample())

    return {"status": "sample_testing_started", "sample": sample_meta}

@app.post("/samples/stop")
def stop_sample_test():
    """Stop sample playback test."""
    audio_engine.stop_sample_test()
    incoming_ai.stop()
    state.is_testing_active = False
    state.active_sample_id = None
    return {"status": "sample_testing_stopped"}

@app.post("/ducking")
def set_ducking(req: DuckingRequest):
    """Update ducking level."""
    audio_engine.set_ducking_factor(req.ducking_factor)
    return {"ducking_factor": audio_engine.ducking_factor}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
