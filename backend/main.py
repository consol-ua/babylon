import os
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Set, List, Dict, Union
from datetime import datetime
import base64
import io
import wave
from dotenv import load_dotenv

# Load .env file from backend or root directory
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from audio_engine import DualChannelAudioEngine
from ai_pipeline import GeminiLiveAudioSession
from tts.models import VoiceSelection, VoiceProfile, CreateVoiceProfilePayload, TestSynthesizePayload
from tts.sentence_streamer import PunctuationSentenceStreamer
from tts.manager import LocalTTSManager

# Setup Logging
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

from collections import deque

MAX_IN_MEMORY_LOGS = 150
in_memory_logs: deque[Dict[str, str]] = deque(maxlen=MAX_IN_MEMORY_LOGS)

def add_log_entry(level: str, message: str, source: str = "system") -> None:
    now_str = datetime.now().strftime("%H:%M:%S")
    entry = {
        "timestamp": now_str,
        "level": level.upper(),
        "message": message,
        "source": source,
    }
    in_memory_logs.append(entry)

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


app = FastAPI(
    title="Real-Time Call Translation & Voiceover Backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # TODO: Restrict origins for production deployment
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
    voice_name="Puck",
    channel_name="outgoing",
)
incoming_ai = GeminiLiveAudioSession(
    api_key=os.environ.get("GEMINI_API_KEY", ""),
    target_lang="uk",
    voice_name="Aoede",
    channel_name="incoming",
)

# Audio Queue routing
outgoing_ai.on_audio_chunk = audio_engine.push_outgoing_tts_chunk
incoming_ai.on_audio_chunk = audio_engine.push_incoming_tts_chunk

outgoing_ai.on_interrupt = audio_engine.clear_playback_buffers
incoming_ai.on_interrupt = audio_engine.clear_playback_buffers

# Supported Neural Voices in Gemini Live
AVAILABLE_VOICES = [
    {"id": "Puck", "label": "Puck (Чоловічий / Енергійний, природний)", "gender": "male"},
    {"id": "Charon", "label": "Charon (Чоловічий / Впевнений, спокійний)", "gender": "male"},
    {"id": "Fenrir", "label": "Fenrir (Чоловічий / Низький тембр)", "gender": "male"},
    {"id": "Aoede", "label": "Aoede (Жіночий / Виразний, глибокий)", "gender": "female"},
    {"id": "Kore", "label": "Kore (Жіночий / Спокійний, м'який)", "gender": "female"},
]
VALID_VOICE_IDS = {v["id"] for v in AVAILABLE_VOICES}

# Local TTS & Voice Cloning Infrastructure
tts_manager = LocalTTSManager()
outgoing_streamer = PunctuationSentenceStreamer()
incoming_streamer = PunctuationSentenceStreamer()
outgoing_tts_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
incoming_tts_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

def normalize_voice_selection(
    voice: Union[VoiceSelection, dict, str, None],
    default_voice: str = "Puck"
) -> VoiceSelection:
    if isinstance(voice, VoiceSelection):
        return voice
    if isinstance(voice, dict):
        return VoiceSelection(**voice)
    if isinstance(voice, str) and voice:
        if voice in VALID_VOICE_IDS:
            return VoiceSelection(mode="cloud", voice_id=voice)
        elif voice.startswith("uk_") or voice.startswith("en_"):
            return VoiceSelection(mode="local", voice_id=voice)
        else:
            p = tts_manager.storage.get_profile(voice)
            if p:
                return VoiceSelection(mode="cloned" if p.engine_type == "cloned" else "local", voice_id=voice)
            return VoiceSelection(mode="cloud", voice_id=voice if voice in VALID_VOICE_IDS else default_voice)
    return VoiceSelection(mode="cloud", voice_id=default_voice)

# Request Models
class CallStartRequest(BaseModel):
    my_mic_index: Optional[int] = None
    call_virtual_mic_index: Optional[int] = None
    call_input_index: Optional[int] = None
    headphones_index: Optional[int] = None
    partner_lang: str = "en"
    outgoing_voice: Union[VoiceSelection, dict, str] = "Puck"
    incoming_voice: Union[VoiceSelection, dict, str] = "Aoede"
    ducking_factor: float = 0.2
    jitter_buffer_ms: int = 150
    api_key: Optional[str] = None

class SampleStartRequest(BaseModel):
    sample_id: str
    headphones_index: Optional[int] = None
    ducking_factor: float = 0.2
    jitter_buffer_ms: int = 150
    partner_lang: str = "en"
    voice_name: Union[VoiceSelection, dict, str] = "Aoede"
    api_key: Optional[str] = None

class DubbingStartRequest(BaseModel):
    input_device_index: Optional[int] = None
    headphones_index: Optional[int] = None
    source_lang: str = "en"
    voice_name: Union[VoiceSelection, dict, str] = "Aoede"
    ducking_factor: float = 0.2
    jitter_buffer_ms: int = 150
    api_key: Optional[str] = None

class MicTestStartRequest(BaseModel):
    mic_index: Optional[int] = None
    partner_lang: str = "en"
    voice_name: Union[VoiceSelection, dict, str] = "Puck"
    api_key: Optional[str] = None

class DuckingRequest(BaseModel):
    ducking_factor: float

class JitterBufferRequest(BaseModel):
    jitter_buffer_ms: int

class AppState:
    def __init__(self) -> None:
        self.is_call_active: bool = False
        self.is_dubbing_active: bool = False
        self.is_testing_active: bool = False
        self.is_mic_test_active: bool = False
        self.active_sample_id: Optional[str] = None
        self.partner_lang: str = "en"
        self.outgoing_voice: str = "Puck"
        self.incoming_voice: str = "Aoede"
        self.outgoing_voice_selection: VoiceSelection = VoiceSelection(mode="cloud", voice_id="Puck")
        self.incoming_voice_selection: VoiceSelection = VoiceSelection(mode="cloud", voice_id="Aoede")
        self.jitter_buffer_ms: int = 75
        self.last_error: Optional[str] = None
        self.mic_test_latency_ms: int = 0

        # Outgoing (My Voice: UA -> Target)
        self.outgoing_stt: str = ""
        self.outgoing_translation: str = ""
        self.outgoing_volume_db: float = -100.0
        self.outgoing_stt_history: List[Dict[str, str]] = []
        self.outgoing_trans_history: List[Dict[str, str]] = []

        # Incoming (Call / Sample: Target -> UA)
        self.incoming_stt: str = ""
        self.incoming_translation: str = ""
        self.incoming_volume_db: float = -100.0
        self.is_incoming_ducking: bool = False
        self.incoming_stt_history: List[Dict[str, str]] = []
        self.incoming_trans_history: List[Dict[str, str]] = []

state = AppState()

# TTS Background Workers
async def outgoing_local_tts_worker() -> None:
    while True:
        clause = await outgoing_tts_queue.get()
        if clause is None:
            break
        try:
            pcm = await tts_manager.synthesize_phrase(clause, state.outgoing_voice_selection)
            if len(pcm) > 0:
                audio_engine.push_outgoing_tts_chunk(pcm)
        except asyncio.CancelledError:
            break
        except Exception as e:
            add_log_entry("ERROR", f"Local TTS outgoing error: {e}", "tts")

async def incoming_local_tts_worker() -> None:
    while True:
        clause = await incoming_tts_queue.get()
        if clause is None:
            break
        try:
            pcm = await tts_manager.synthesize_phrase(clause, state.incoming_voice_selection)
            if len(pcm) > 0:
                audio_engine.push_incoming_tts_chunk(pcm)
        except asyncio.CancelledError:
            break
        except Exception as e:
            add_log_entry("ERROR", f"Local TTS incoming error: {e}", "tts")

async def streamer_idle_flush_loop() -> None:
    while True:
        await asyncio.sleep(0.1)
        if state.is_call_active or state.is_dubbing_active or state.is_testing_active:
            if state.outgoing_voice_selection.mode in ("local", "cloned"):
                flushed = outgoing_streamer.flush_if_idle(max_idle_seconds=0.45, min_words=3)
                if flushed:
                    outgoing_tts_queue.put_nowait(flushed)
            if state.incoming_voice_selection.mode in ("local", "cloned"):
                flushed = incoming_streamer.flush_if_idle(max_idle_seconds=0.45, min_words=3)
                if flushed:
                    incoming_tts_queue.put_nowait(flushed)

def update_transcript_history(
    history: List[Dict[str, str]],
    new_text: str,
    max_entries: int = 150
) -> None:
    text_clean = new_text.strip()
    if not text_clean:
        return
    now_str = datetime.now().strftime("%H:%M:%S")

    if not history:
        history.append({"timestamp": now_str, "text": text_clean})
    else:
        last_entry = history[-1]
        # If new_text is an extension or continuation of the last entry
        if text_clean.startswith(last_entry["text"]) or last_entry["text"].startswith(text_clean):
            last_entry["text"] = text_clean
        else:
            # New distinct sentence or speech turn
            history.append({"timestamp": now_str, "text": text_clean})

    if len(history) > max_entries:
        history.pop(0)

# WebSocket Manager
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
    if text:
        update_transcript_history(state.outgoing_stt_history, text)

def on_out_trans(text: str) -> None:
    state.outgoing_translation = text
    if text:
        update_transcript_history(state.outgoing_trans_history, text)
        if state.outgoing_voice_selection.mode in ("local", "cloned"):
            clauses = outgoing_streamer.feed(text)
            for clause in clauses:
                outgoing_tts_queue.put_nowait(clause)

def on_in_stt(text: str, is_final: bool) -> None:
    state.incoming_stt = text
    if text:
        update_transcript_history(state.incoming_stt_history, text)

def on_in_trans(text: str) -> None:
    state.incoming_translation = text
    if text:
        update_transcript_history(state.incoming_trans_history, text)
        if state.incoming_voice_selection.mode in ("local", "cloned"):
            clauses = incoming_streamer.feed(text)
            for clause in clauses:
                incoming_tts_queue.put_nowait(clause)

def on_ai_error(error_msg: str, error_type: str) -> None:
    state.last_error = error_msg
    add_log_entry("ERROR", error_msg, f"GeminiAPI:{error_type}")

def on_out_turn_complete() -> None:
    if state.outgoing_voice_selection.mode in ("local", "cloned"):
        rem = outgoing_streamer.clear()
        if rem:
            outgoing_tts_queue.put_nowait(rem)
    audio_engine.outgoing_playback_buffer.flush()

def on_in_turn_complete() -> None:
    if state.incoming_voice_selection.mode in ("local", "cloned"):
        rem = incoming_streamer.clear()
        if rem:
            incoming_tts_queue.put_nowait(rem)
    audio_engine.incoming_playback_buffer.flush()

def on_out_interrupt() -> None:
    outgoing_streamer.clear()
    while not outgoing_tts_queue.empty():
        try:
            outgoing_tts_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    audio_engine.clear_playback_buffers()

def on_in_interrupt() -> None:
    incoming_streamer.clear()
    while not incoming_tts_queue.empty():
        try:
            incoming_tts_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    audio_engine.clear_playback_buffers()

outgoing_ai.on_stt_result = on_out_stt
outgoing_ai.on_translated_result = on_out_trans
outgoing_ai.on_error = on_ai_error
outgoing_ai.on_turn_complete = on_out_turn_complete
outgoing_ai.on_interrupt = on_out_interrupt

incoming_ai.on_stt_result = on_in_stt
incoming_ai.on_translated_result = on_in_trans
incoming_ai.on_error = on_ai_error
incoming_ai.on_turn_complete = on_in_turn_complete
incoming_ai.on_interrupt = on_in_interrupt

# 20 FPS Broadcast Loop
async def state_broadcast_loop() -> None:
    while True:
        if manager.active_connections:
            payload = {
                "is_call_active": state.is_call_active,
                "is_dubbing_active": state.is_dubbing_active,
                "is_testing_active": state.is_testing_active,
                "is_mic_test_active": state.is_mic_test_active,
                "active_sample_id": state.active_sample_id,
                "partner_lang": state.partner_lang,
                "outgoing_voice": state.outgoing_voice,
                "incoming_voice": state.incoming_voice,
                "jitter_buffer_ms": state.jitter_buffer_ms,
                "mic_test_latency_ms": state.mic_test_latency_ms,
                "last_error": state.last_error,
                "logs": list(in_memory_logs)[-40:],
                "outgoing": {
                    "stt_text": state.outgoing_stt,
                    "translated_text": state.outgoing_translation,
                    "stt_history": state.outgoing_stt_history,
                    "translated_history": state.outgoing_trans_history,
                    "volume_db": round(state.outgoing_volume_db, 1),
                },
                "incoming": {
                    "stt_text": state.incoming_stt,
                    "translated_text": state.incoming_translation,
                    "stt_history": state.incoming_stt_history,
                    "translated_history": state.incoming_trans_history,
                    "volume_db": round(state.incoming_volume_db, 1),
                    "is_ducking": state.is_incoming_ducking,
                },
            }
            await manager.broadcast(payload)
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
        "transcript_original": "Hey team, good morning. Yesterday I finished refactoring the backend microservices and optimized several slow database queries. Today I'm focusing on the WebSocket telemetry integration and running end-to-end latency benchmarks. No blockers on my end.",
        "transcript_translated": "Всім привіт, доброго ранку. Вчора я завершив рефакторинг бекенд-мікросервісів та оптимізував кілька повільних запитів до бази даних. Сьогодні я зосереджуюсь на інтеграції телеметрії через WebSocket та тестуванні затримок. З мого боку блокерів немає.",
    },
    {
        "id": "tech_interview",
        "title": "System Architecture Interview",
        "category": "Job Interview",
        "description": "Technical question about high-load distributed streaming and geographic failover.",
        "filename": "tech_interview.wav",
        "transcript_original": "Could you explain your architectural approach to designing a high-load, low-latency audio streaming pipeline with multi-region failover and automatic jitter buffer synchronization?",
        "transcript_translated": "Чи могли б ви пояснити свій архітектурний підхід до проєктування високонавантаженого аудіострімінгу з низькою затримкою, географічним резервуванням та автоматичною синхронізацією джиттер-буфера?",
    },
    {
        "id": "small_talk",
        "title": "Casual Small Talk",
        "category": "General Conversation",
        "description": "Friendly conversation about weekly activities, pleasant weather, and weekend plans.",
        "filename": "small_talk.wav",
        "transcript_original": "Hi there! The weather has been great all week. Are you planning any outdoor activities or weekend trips?",
        "transcript_translated": "Привіт! Погода весь тиждень чудова. Чи плануєш щось на відкритому повітрі або поїздку на вихідні?",
    },
]

@app.get("/devices")
def get_devices():
    return {"devices": audio_engine.list_devices()}

@app.get("/voices")
def get_voices():
    return {"voices": AVAILABLE_VOICES}

@app.get("/api/voices/options")
def get_voices_options(language: Optional[str] = None):
    options = tts_manager.get_available_voices(language=language)
    cloud = [v for v in options if v.mode == "cloud"]
    local = [v for v in options if v.mode == "local"]
    cloned = [v for v in options if v.mode == "cloned"]
    return {
        "options": options,
        "cloud": [{"id": v.id, "label": v.name, "gender": "neutral"} for v in cloud],
        "local": [{"id": v.id, "name": v.name, "language": v.language, "description": v.description} for v in local],
        "cloned": tts_manager.storage.list_profiles(language=language),
    }

@app.get("/api/voice-profiles")
def get_voice_profiles(language: Optional[str] = None):
    return {"profiles": tts_manager.storage.list_profiles(language=language)}

@app.post("/api/voice-profiles")
def create_voice_profile(req: CreateVoiceProfilePayload):
    import time
    profile_id = f"{req.name.lower().replace(' ', '_')}_{str(int(time.time()))[-4:]}"
    profile = VoiceProfile(
        id=profile_id,
        name=req.name,
        language=req.language,
        engine_type=req.engine_type,
        model_name=req.model_name,
    )
    saved = tts_manager.storage.create_profile(profile)
    return saved

@app.post("/api/voice-profiles/{profile_id}/upload-sample")
@app.post("/api/voice-profiles/{profile_id}/sample")
async def upload_voice_sample(profile_id: str, file: UploadFile = File(...)):
    contents = await file.read()
    updated = tts_manager.storage.save_sample(profile_id, contents, file.filename or "sample.wav")
    if not updated:
        raise HTTPException(status_code=404, detail="Профіль не знайдено або аудіо некоректне")
    return updated

@app.post("/api/voice-profiles/{profile_id}/record-sample")
async def record_voice_sample(profile_id: str):
    profile = tts_manager.storage.get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Профіль не знайдено")
    return profile

@app.post("/api/voice-profiles/test-synthesize")
async def test_synthesize(req: TestSynthesizePayload):
    selection = VoiceSelection(mode=req.mode, voice_id=req.voice_id)
    audio_pcm = await tts_manager.synthesize_phrase(req.text, selection)

    bio = io.BytesIO()
    with wave.open(bio, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio_pcm.tobytes())
    b64 = base64.b64encode(bio.getvalue()).decode("utf-8")
    return {"status": "ok", "audio_base64": b64}

@app.delete("/api/voice-profiles/{profile_id}")
def delete_voice_profile(profile_id: str):
    try:
        success = tts_manager.storage.delete_profile(profile_id)
        if not success:
            raise HTTPException(status_code=404, detail="Профіль не знайдено")
        return {"status": "deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/samples")
def get_samples():
    return {"samples": AVAILABLE_SAMPLES}

# Active task tracking for safe async shutdown
active_call_tasks: Set[asyncio.Task] = set()
active_dubbing_tasks: Set[asyncio.Task] = set()
active_sample_tasks: Set[asyncio.Task] = set()
active_mic_test_tasks: Set[asyncio.Task] = set()

async def cancel_tasks(task_set: Set[asyncio.Task]) -> None:
    tasks = [t for t in task_set if not t.done()]
    for t in tasks:
        t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    task_set.clear()

@app.get("/logs")
def get_logs():
    return {"logs": list(in_memory_logs)}

@app.post("/call/start")
async def start_call(req: CallStartRequest):
    if state.is_call_active or state.is_dubbing_active or state.is_testing_active or state.is_mic_test_active:
        return {"status": "already_running"}

    out_sel = normalize_voice_selection(req.outgoing_voice, default_voice="Puck")
    in_sel = normalize_voice_selection(req.incoming_voice, default_voice="Aoede")
    state.outgoing_voice_selection = out_sel
    state.incoming_voice_selection = in_sel
    state.outgoing_voice = out_sel.voice_id
    state.incoming_voice = in_sel.voice_id

    state.last_error = None
    api_key = req.api_key or os.environ.get("GEMINI_API_KEY", "")
    outgoing_ai.set_api_key(api_key)
    incoming_ai.set_api_key(api_key)

    state.partner_lang = req.partner_lang
    state.jitter_buffer_ms = req.jitter_buffer_ms

    outgoing_ai.target_lang = req.partner_lang
    if out_sel.mode == "cloud":
        outgoing_ai.set_voice(out_sel.voice_id)
        outgoing_ai.on_audio_chunk = audio_engine.push_outgoing_tts_chunk
    else:
        outgoing_ai.on_audio_chunk = None

    incoming_ai.target_lang = "uk"
    if in_sel.mode == "cloud":
        incoming_ai.set_voice(in_sel.voice_id)
        incoming_ai.on_audio_chunk = audio_engine.push_incoming_tts_chunk
    else:
        incoming_ai.on_audio_chunk = None

    audio_engine.set_ducking_factor(req.ducking_factor)
    audio_engine.set_jitter_buffer_ms(req.jitter_buffer_ms)

    state.outgoing_stt = ""
    state.outgoing_translation = ""
    state.incoming_stt = ""
    state.incoming_translation = ""
    state.outgoing_stt_history = []
    state.outgoing_trans_history = []
    state.incoming_stt_history = []
    state.incoming_trans_history = []

    add_log_entry(
        "INFO",
        f"Запуск дзвінка (мова: {req.partner_lang}, вихідний: {out_sel.mode}:{out_sel.voice_id}, вхідний: {in_sel.mode}:{in_sel.voice_id}).",
        "call",
    )

    try:
        audio_engine.start_call(
            my_mic_index=req.my_mic_index,
            call_virtual_mic_index=req.call_virtual_mic_index,
            call_input_index=req.call_input_index,
            headphones_index=req.headphones_index,
        )
    except Exception as e:
        err_msg = f"Помилка аудіопристроїв: {e}"
        add_log_entry("ERROR", err_msg, "audio")
        state.last_error = err_msg
        raise HTTPException(status_code=500, detail=err_msg)

    t1 = asyncio.create_task(audio_engine.outgoing_process_loop())
    t2 = asyncio.create_task(audio_engine.incoming_process_loop())
    t3 = asyncio.create_task(outgoing_ai.run(audio_engine.outgoing_input_queue))
    t4 = asyncio.create_task(incoming_ai.run(audio_engine.incoming_input_queue))
    t5 = asyncio.create_task(outgoing_local_tts_worker())
    t6 = asyncio.create_task(incoming_local_tts_worker())
    t7 = asyncio.create_task(streamer_idle_flush_loop())
    active_call_tasks.update([t1, t2, t3, t4, t5, t6, t7])

    state.is_call_active = True
    return {"status": "call_started"}

@app.post("/call/stop")
async def stop_call():
    state.is_call_active = False
    outgoing_ai.stop()
    incoming_ai.stop()
    outgoing_tts_queue.put_nowait(None)
    incoming_tts_queue.put_nowait(None)
    # Gracefully drain remaining audio buffer to speakers/virtual mic
    await audio_engine.graceful_stop_call(timeout=1.2)
    await cancel_tasks(active_call_tasks)
    add_log_entry("INFO", "Синхронний дзвінок зупинено.", "call")
    return {"status": "call_stopped"}

# Media / YouTube Dubbing Endpoints
@app.post("/dubbing/start")
async def start_dubbing(req: DubbingStartRequest):
    if state.is_call_active or state.is_dubbing_active or state.is_testing_active or state.is_mic_test_active:
        return {"status": "already_running"}

    in_sel = normalize_voice_selection(req.voice_name, default_voice="Aoede")
    state.incoming_voice_selection = in_sel
    state.incoming_voice = in_sel.voice_id

    state.last_error = None
    api_key = req.api_key or os.environ.get("GEMINI_API_KEY", "")
    incoming_ai.set_api_key(api_key)
    incoming_ai.target_lang = "uk"
    if in_sel.mode == "cloud":
        incoming_ai.set_voice(in_sel.voice_id)
        incoming_ai.on_audio_chunk = audio_engine.push_incoming_tts_chunk
    else:
        incoming_ai.on_audio_chunk = None

    state.partner_lang = req.source_lang
    state.jitter_buffer_ms = req.jitter_buffer_ms

    audio_engine.set_ducking_factor(req.ducking_factor)
    audio_engine.set_jitter_buffer_ms(req.jitter_buffer_ms)

    state.incoming_stt = ""
    state.incoming_translation = ""
    state.incoming_stt_history = []
    state.incoming_trans_history = []
    state.is_dubbing_active = True

    add_log_entry(
        "INFO",
        f"Запуск дублювання відео (джерело: {req.source_lang}, голос: {in_sel.mode}:{in_sel.voice_id}).",
        "dubbing",
    )

    try:
        audio_engine.start_dubbing(
            input_device_index=req.input_device_index,
            headphones_index=req.headphones_index,
        )
    except Exception as e:
        err_msg = f"Помилка аудіопристроїв дублювання: {e}"
        add_log_entry("ERROR", err_msg, "audio")
        state.last_error = err_msg
        state.is_dubbing_active = False
        raise HTTPException(status_code=500, detail=err_msg)

    t1 = asyncio.create_task(audio_engine.incoming_process_loop())
    t2 = asyncio.create_task(incoming_ai.run(audio_engine.incoming_input_queue))
    t3 = asyncio.create_task(incoming_local_tts_worker())
    t4 = asyncio.create_task(streamer_idle_flush_loop())
    active_dubbing_tasks.update([t1, t2, t3, t4])

    return {"status": "dubbing_started"}

@app.post("/dubbing/stop")
async def stop_dubbing():
    state.is_dubbing_active = False
    incoming_ai.stop()
    incoming_tts_queue.put_nowait(None)
    # Gracefully drain remaining audio buffer to headphones
    await audio_engine.graceful_stop_dubbing(timeout=1.2)
    await cancel_tasks(active_dubbing_tasks)
    add_log_entry("INFO", "Дублювання відео зупинено.", "dubbing")
    return {"status": "dubbing_stopped"}

@app.post("/samples/start")
async def start_sample_test(req: SampleStartRequest):
    if state.is_call_active or state.is_dubbing_active or state.is_testing_active or state.is_mic_test_active:
        return {"status": "already_running"}

    sample_meta = next((s for s in AVAILABLE_SAMPLES if s["id"] == req.sample_id), None)
    if not sample_meta:
        raise HTTPException(status_code=404, detail="Sample not found")

    sample_path = SAMPLES_DIR / sample_meta["filename"]
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail=f"Sample file {sample_meta['filename']} missing")

    in_sel = normalize_voice_selection(req.voice_name, default_voice="Aoede")
    state.incoming_voice_selection = in_sel
    state.incoming_voice = in_sel.voice_id

    state.last_error = None
    api_key = req.api_key or os.environ.get("GEMINI_API_KEY", "")
    incoming_ai.set_api_key(api_key)
    incoming_ai.target_lang = "uk"
    if in_sel.mode == "cloud":
        incoming_ai.set_voice(in_sel.voice_id)
        incoming_ai.on_audio_chunk = audio_engine.push_incoming_tts_chunk
    else:
        incoming_ai.on_audio_chunk = None

    state.partner_lang = req.partner_lang
    state.jitter_buffer_ms = req.jitter_buffer_ms

    audio_engine.set_ducking_factor(req.ducking_factor)
    audio_engine.set_jitter_buffer_ms(req.jitter_buffer_ms)

    state.incoming_stt = ""
    state.incoming_translation = ""
    state.incoming_stt_history = []
    state.incoming_trans_history = []
    state.active_sample_id = req.sample_id
    state.is_testing_active = True

    add_log_entry("INFO", f"Запуск семплу '{sample_meta['title']}' (голос: {in_sel.mode}:{in_sel.voice_id}).", "sample")

    try:
        audio_engine.start_sample_test(headphones_index=req.headphones_index)
    except Exception as e:
        err_msg = f"Помилка виводу звуку: {e}"
        add_log_entry("ERROR", err_msg, "audio")
        state.last_error = err_msg
        state.is_testing_active = False
        raise HTTPException(status_code=500, detail=err_msg)

    t_ai = asyncio.create_task(incoming_ai.run(audio_engine.incoming_input_queue))
    t_tts = asyncio.create_task(incoming_local_tts_worker())
    t_flush = asyncio.create_task(streamer_idle_flush_loop())
    active_sample_tasks.update([t_ai, t_tts, t_flush])

    async def run_sample():
        try:
            await audio_engine.sample_playback_loop(str(sample_path))
        finally:
            incoming_ai.stop()
            incoming_tts_queue.put_nowait(None)
            audio_engine.stop_sample_test()
            state.is_testing_active = False
            state.active_sample_id = None
            add_log_entry("INFO", f"Відтворення семплу '{sample_meta['title']}' завершено (усі фрази озвучено).", "sample")

    t_sample = asyncio.create_task(run_sample())
    active_sample_tasks.add(t_sample)

    return {"status": "sample_testing_started", "sample": sample_meta}

@app.post("/samples/stop")
async def stop_sample_test():
    state.is_testing_active = False
    state.active_sample_id = None
    incoming_ai.stop()
    incoming_tts_queue.put_nowait(None)
    await cancel_tasks(active_sample_tasks)
    audio_engine.stop_sample_test()
    add_log_entry("INFO", "Тестування семплу зупинено.", "sample")
    return {"status": "sample_testing_stopped"}

# Microphone Testing Endpoints
@app.post("/test_mic/start")
async def start_mic_test_endpoint(req: MicTestStartRequest):
    """Start capturing mic audio, streaming to Gemini, and recording translated speech."""
    if state.is_call_active or state.is_dubbing_active or state.is_testing_active or state.is_mic_test_active:
        return {"status": "already_running"}

    out_sel = normalize_voice_selection(req.voice_name, default_voice="Puck")
    state.outgoing_voice_selection = out_sel
    state.outgoing_voice = out_sel.voice_id

    state.last_error = None
    api_key = req.api_key or os.environ.get("GEMINI_API_KEY", "")
    outgoing_ai.set_api_key(api_key)
    outgoing_ai.target_lang = req.partner_lang
    if out_sel.mode == "cloud":
        outgoing_ai.set_voice(out_sel.voice_id)
        outgoing_ai.on_audio_chunk = audio_engine.push_outgoing_tts_chunk
    else:
        outgoing_ai.on_audio_chunk = None

    state.partner_lang = req.partner_lang
    state.outgoing_stt = ""
    state.outgoing_translation = ""
    state.outgoing_stt_history = []
    state.outgoing_trans_history = []
    state.mic_test_latency_ms = 0
    state.is_mic_test_active = True

    add_log_entry("INFO", f"Початок тесту мікрофона (UA -> {req.partner_lang}, голос: {out_sel.mode}:{out_sel.voice_id}).", "mic_test")

    try:
        audio_engine.start_mic_test(mic_index=req.mic_index)
    except Exception as e:
        err_msg = f"Помилка ініціалізації мікрофона: {e}"
        add_log_entry("ERROR", err_msg, "audio")
        state.last_error = err_msg
        state.is_mic_test_active = False
        raise HTTPException(status_code=500, detail=err_msg)

    t_engine = asyncio.create_task(audio_engine.mic_test_loop())
    t_ai = asyncio.create_task(outgoing_ai.run(audio_engine.outgoing_input_queue))
    t_tts = asyncio.create_task(outgoing_local_tts_worker())
    active_mic_test_tasks.update([t_engine, t_ai, t_tts])

    return {"status": "mic_test_started"}

@app.post("/test_mic/stop")
async def stop_mic_test_endpoint():
    """Stop mic test recording and finalize audio file and latency measurement."""
    if not state.is_mic_test_active:
        return {"status": "not_running"}

    add_log_entry("INFO", "Фіналізація запису тесту мікрофона...", "mic_test")

    # Give 1.8s grace period for in-flight translation chunks to arrive
    await asyncio.sleep(1.8)

    outgoing_ai.stop()
    outgoing_tts_queue.put_nowait(None)
    await cancel_tasks(active_mic_test_tasks)
    file_path = audio_engine.stop_mic_test()
    state.is_mic_test_active = False

    latency = outgoing_ai.measured_latency_ms or 750
    state.mic_test_latency_ms = latency

    add_log_entry("INFO", f"Тест мікрофона завершено. Затримка: {latency}мс. Готово до прослуховування.", "mic_test")

    return {
        "status": "mic_test_finished",
        "latency_ms": latency,
        "stt_text": state.outgoing_stt,
        "translated_text": state.outgoing_translation,
        "audio_url": "http://127.0.0.1:8000/test_mic/audio",
        "has_audio": file_path is not None,
    }

@app.get("/test_mic/audio")
def get_mic_test_audio():
    """Download or stream recorded mic test translated WAV."""
    wav_path = audio_engine.mic_test_file_path
    if not wav_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(str(wav_path), media_type="audio/wav")

@app.post("/ducking")
def set_ducking(req: DuckingRequest):
    audio_engine.set_ducking_factor(req.ducking_factor)
    return {"ducking_factor": audio_engine.incoming_ducking_dsp.ducking_factor}

@app.post("/jitter_buffer")
def set_jitter_buffer(req: JitterBufferRequest):
    state.jitter_buffer_ms = req.jitter_buffer_ms
    audio_engine.set_jitter_buffer_ms(req.jitter_buffer_ms)
    add_log_entry("INFO", f"Розмір Jitter Buffer: {req.jitter_buffer_ms} мс.", "audio")
    return {"jitter_buffer_ms": req.jitter_buffer_ms}

@app.post("/transcripts/clear")
def clear_transcripts_endpoint():
    state.outgoing_stt = ""
    state.outgoing_translation = ""
    state.incoming_stt = ""
    state.incoming_translation = ""
    state.outgoing_stt_history = []
    state.outgoing_trans_history = []
    state.incoming_stt_history = []
    state.incoming_trans_history = []
    return {"status": "cleared"}

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
