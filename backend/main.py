import asyncio
from typing import List, Optional, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from audio_engine import AudioEngine
from ai_pipeline import AIPipeline

app = FastAPI(title="Voiceover & Translation Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Engine Instances
audio_engine = AudioEngine()
ai_pipeline = AIPipeline()

# State models
class StartRequest(BaseModel):
    input_device_index: Optional[int] = None
    output_device_index: Optional[int] = None
    source_lang: str = "en-US"
    target_lang: str = "uk"

class DuckingRequest(BaseModel):
    ducking_factor: float

class AppState:
    def __init__(self) -> None:
        self.is_translating: bool = False
        self.current_stt: str = ""
        self.current_translation: str = ""
        self.volume_level_db: float = -100.0
        self.is_ducking: bool = False

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

# Link Callbacks
def on_telemetry(db: float, is_ducking: bool) -> None:
    state.volume_level_db = db
    state.is_ducking = is_ducking

def on_stt_result(text: str, is_final: bool) -> None:
    state.current_stt = text

def on_translated_result(text: str) -> None:
    state.current_translation = text

audio_engine.telemetry_callback = on_telemetry
ai_pipeline.on_stt_result = on_stt_result
ai_pipeline.on_translated_result = on_translated_result

# Background loop to broadcast state to clients over WebSocket
async def state_broadcast_loop() -> None:
    while True:
        if manager.active_connections:
            await manager.broadcast(
                {
                    "is_translating": state.is_translating,
                    "stt_text": state.current_stt,
                    "translated_text": state.current_translation,
                    "volume_db": round(state.volume_level_db, 1),
                    "is_ducking": state.is_ducking,
                }
            )
        await asyncio.sleep(0.05)  # 20 FPS updates

@app.on_event("startup")
async def startup_event() -> None:
    asyncio.create_task(state_broadcast_loop())

@app.get("/devices")
def get_devices():
    """List available audio input and output devices."""
    return {"devices": audio_engine.list_devices()}

@app.post("/start")
async def start_pipeline(req: StartRequest):
    """Start audio capture, translation, and mixing."""
    if state.is_translating:
        return {"status": "already_running"}

    ai_pipeline.source_lang = req.source_lang
    ai_pipeline.target_lang = req.target_lang

    audio_engine.start(
        input_device_index=req.input_device_index,
        output_device_index=req.output_device_index,
    )
    
    # Launch async workers
    asyncio.create_task(audio_engine.process_loop())
    asyncio.create_task(
        ai_pipeline.run(audio_engine.input_queue, audio_engine.tts_playback_queue)
    )

    state.is_translating = True
    return {"status": "started"}

@app.post("/stop")
def stop_pipeline():
    """Stop audio capture and AI processing."""
    audio_engine.stop()
    ai_pipeline.stop()
    state.is_translating = False
    return {"status": "stopped"}

@app.post("/ducking")
def set_ducking(req: DuckingRequest):
    """Update audio ducking factor (0.0 - 1.0)."""
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
