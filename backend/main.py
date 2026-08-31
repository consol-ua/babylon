import os
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Set, List, Dict
from datetime import datetime
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

# Setup Logging to file and memory
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOGS_DIR / "app.log"

logger = logging.getLogger("gemini_translator")
logger.setLevel(logging.INFO)
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
file_handler.setFormatter(
    logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s")
)
logger.addHandler(file_handler)

MAX_IN_MEMORY_LOGS = 150
in_memory_logs: List[Dict[str, str]] = []

def add_log_entry(level: str, message: str, source: str = "system") -> None:
    now_str = datetime.now().strftime("%H:%M:%S")
    entry = {
        "timestamp": now_str,
        "level": level.upper(),
        "message": message,
        "source": source,
    }
    in_memory_logs.append(entry)
    if len(in_memory_logs) > MAX_IN_MEMORY_LOGS:
        in_memory_logs.pop(0)

    if level.upper() == "ERROR":
        logger.error(f"[{source}] {message}")
    elif level.upper() == "WARN":
        logger.warning(f"[{source}] {message}")
    else:
        logger.info(f"[{source}] {message}")

add_log_entry("INFO", "Сервер перекладача успішно ініціалізовано.", "system")


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
        await audio_engine.terminate()


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

# Audio Queue routing
outgoing_ai.on_audio_chunk = audio_engine.push_outgoing_tts_chunk
incoming_ai.on_audio_chunk = audio_engine.push_incoming_tts_chunk

outgoing_ai.on_interrupt = audio_engine.clear_playback_buffers
incoming_ai.on_interrupt = audio_engine.clear_playback_buffers

# Request Models
class CallStartRequest(BaseModel):
    my_mic_index: Optional[int] = None
    call_virtual_mic_index: Optional[int] = None
    call_input_index: Optional[int] = None
    headphones_index: Optional[int] = None
    partner_lang: str = "en"
    ducking_factor: float = 0.2
    jitter_buffer_ms: int = 150
    api_key: Optional[str] = None

class SampleStartRequest(BaseModel):
    sample_id: str
    headphones_index: Optional[int] = None
    ducking_factor: float = 0.2
    jitter_buffer_ms: int = 150
    partner_lang: str = "en"
    api_key: Optional[str] = None

class DuckingRequest(BaseModel):
    ducking_factor: float

class JitterBufferRequest(BaseModel):
    jitter_buffer_ms: int

class AppState:
    def __init__(self) -> None:
        self.is_call_active: bool = False
        self.is_testing_active: bool = False
        self.active_sample_id: Optional[str] = None
        self.partner_lang: str = "en"
        self.jitter_buffer_ms: int = 150
        self.last_error: Optional[str] = None

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

def on_ai_error(error_msg: str, error_type: str) -> None:
    state.last_error = error_msg
    add_log_entry("ERROR", error_msg, f"GeminiAPI:{error_type}")

outgoing_ai.on_stt_result = on_out_stt
outgoing_ai.on_translated_result = on_out_trans
outgoing_ai.on_error = on_ai_error

incoming_ai.on_stt_result = on_in_stt
incoming_ai.on_translated_result = on_in_trans
incoming_ai.on_error = on_ai_error

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
                    "jitter_buffer_ms": state.jitter_buffer_ms,
                    "last_error": state.last_error,
                    "logs": in_memory_logs[-40:],
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

@app.get("/logs")
def get_logs():
    """Get latest in-memory logs."""
    return {"logs": in_memory_logs}

@app.post("/call/start")
async def start_call(req: CallStartRequest):
    """Start full-duplex bidirectional call translation."""
    if state.is_call_active or state.is_testing_active:
        return {"status": "already_running"}

    state.last_error = None
    api_key = req.api_key or os.environ.get("GEMINI_API_KEY", "")
    outgoing_ai.set_api_key(api_key)
    incoming_ai.set_api_key(api_key)

    state.partner_lang = req.partner_lang
    state.jitter_buffer_ms = req.jitter_buffer_ms
    outgoing_ai.target_lang = req.partner_lang
    incoming_ai.target_lang = "uk"

    audio_engine.set_ducking_factor(req.ducking_factor)
    audio_engine.set_jitter_buffer_ms(req.jitter_buffer_ms)

    state.outgoing_stt = ""
    state.outgoing_translation = ""
    state.incoming_stt = ""
    state.incoming_translation = ""

    add_log_entry("INFO", f"Запуск синхронного дзвінка (мову співрозмовника: {req.partner_lang}, буфер: {req.jitter_buffer_ms}мс, ducking: {int(req.ducking_factor*100)}%).", "call")

    try:
        audio_engine.start_call(
            my_mic_index=req.my_mic_index,
            call_virtual_mic_index=req.call_virtual_mic_index,
            call_input_index=req.call_input_index,
            headphones_index=req.headphones_index,
        )
    except Exception as e:
        err_msg = f"Помилка ініціалізації аудіопристроїв: {e}"
        add_log_entry("ERROR", err_msg, "audio")
        state.last_error = err_msg
        raise HTTPException(status_code=500, detail=err_msg)

    asyncio.create_task(audio_engine.outgoing_process_loop())
    asyncio.create_task(audio_engine.incoming_process_loop())

    asyncio.create_task(outgoing_ai.run(audio_engine.outgoing_input_queue))
    asyncio.create_task(incoming_ai.run(audio_engine.incoming_input_queue))

    state.is_call_active = True
    return {"status": "call_started"}

@app.post("/call/stop")
async def stop_call():
    """Stop live call session."""
    await audio_engine.stop_call()
    outgoing_ai.stop()
    incoming_ai.stop()
    state.is_call_active = False
    add_log_entry("INFO", "Синхронний дзвінок зупинено.", "call")
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

    state.last_error = None
    api_key = req.api_key or os.environ.get("GEMINI_API_KEY", "")
    incoming_ai.set_api_key(api_key)
    incoming_ai.target_lang = "uk"
    state.partner_lang = req.partner_lang
    state.jitter_buffer_ms = req.jitter_buffer_ms

    audio_engine.set_ducking_factor(req.ducking_factor)
    audio_engine.set_jitter_buffer_ms(req.jitter_buffer_ms)

    state.incoming_stt = ""
    state.incoming_translation = ""
    state.active_sample_id = req.sample_id
    state.is_testing_active = True

    add_log_entry("INFO", f"Запуск тестування семплу '{sample_meta['title']}' (буфер: {req.jitter_buffer_ms}мс, ducking: {int(req.ducking_factor*100)}%).", "sample")

    try:
        audio_engine.start_sample_test(headphones_index=req.headphones_index)
    except Exception as e:
        err_msg = f"Помилка ініціалізації виводу звуку в навушники: {e}"
        add_log_entry("ERROR", err_msg, "audio")
        state.last_error = err_msg
        state.is_testing_active = False
        raise HTTPException(status_code=500, detail=err_msg)

    asyncio.create_task(incoming_ai.run(audio_engine.incoming_input_queue))

    async def run_sample():
        try:
            await audio_engine.sample_playback_loop(str(sample_path))
        finally:
            incoming_ai.stop()
            await audio_engine.stop_sample_test()
            state.is_testing_active = False
            state.active_sample_id = None
            add_log_entry("INFO", f"Відтворення семплу '{sample_meta['title']}' завершено.", "sample")

    asyncio.create_task(run_sample())

    return {"status": "sample_testing_started", "sample": sample_meta}

@app.post("/samples/stop")
async def stop_sample_test():
    """Stop sample playback test."""
    await audio_engine.stop_sample_test()
    incoming_ai.stop()
    state.is_testing_active = False
    state.active_sample_id = None
    add_log_entry("INFO", "Тестування семплу зупинено користувачем.", "sample")
    return {"status": "sample_testing_stopped"}

@app.post("/ducking")
def set_ducking(req: DuckingRequest):
    """Update ducking level."""
    audio_engine.set_ducking_factor(req.ducking_factor)
    return {"ducking_factor": audio_engine.incoming_ducking_dsp.ducking_factor}

@app.post("/jitter_buffer")
def set_jitter_buffer(req: JitterBufferRequest):
    """Update jitter buffer cushion size in milliseconds."""
    state.jitter_buffer_ms = req.jitter_buffer_ms
    audio_engine.set_jitter_buffer_ms(req.jitter_buffer_ms)
    add_log_entry("INFO", f"Розмір Jitter Buffer оновлено: {req.jitter_buffer_ms} мс.", "audio")
    return {"jitter_buffer_ms": req.jitter_buffer_ms}

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
