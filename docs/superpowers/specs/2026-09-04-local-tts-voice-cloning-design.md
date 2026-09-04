# Design Specification: Local TTS & Voice Cloning Integration

**Date:** 2026-09-04  
**Status:** Approved  
**Author:** Antigravity Team  
**Scope:** Real-Time Call Translation with Local Neural TTS & Voice Cloning  

---

## 1. Executive Summary

The **Gemini Live Duo Translator** currently provides bidirectional simultaneous translation using the Gemini Multimodal Live API (`gemini-3.5-live-translate-preview`). Speech synthesis (TTS) has previously been restricted to Google Cloud neural voices (`Puck`, `Charon`, `Fenrir`, `Aoede`, `Kore`).

This specification defines the architecture, components, data flows, and interfaces required to introduce **Local Speech Synthesis (Local TTS)** with a scalable foundation for **Zero-Shot Voice Cloning** on macOS Apple Silicon (M1 Pro and above). The system retains the low-latency cloud STT and translation intelligence from Gemini Live, while delegating audio generation to a pluggable local speech synthesis engine.

---

## 2. Architecture & System Decomposition

### 2.1. Hybrid Architecture Overview

The system operates in a **Hybrid Mode**:
* **Gemini Live Engine:** Handles continuous Speech-to-Text (STT) and streaming translation into text tokens with ~200–300 ms response time.
* **Punctuation Sentence Streamer:** Chunks streaming tokens by punctuation boundaries for natural prosody without incurring full-paragraph latency.
* **Local TTS Manager:** Selects the designated provider (`Gemini Cloud Audio`, `Piper TTS (ONNX)`, or `Cloned Voice (Zero-Shot)`).
* **DualChannelAudioEngine:** Accepts 16 kHz 16-bit mono PCM chunks, manages jitter buffering (`AudioStreamBuffer`), and applies DSP Smart Ducking before feeding virtual output devices (`BlackHole 2ch` for Zoom, physical headphones for local listening).

```text
               +-------------------------------------------------+
               |              Gemini Live API Session            |
               +-------------------------------------------------+
                                        |
                 (Real-time Translated Text Tokens / Phrases)
                                        v
               +-------------------------------------------------+
               |          PunctuationSentenceStreamer            |
               | (Splits on punctuation / pauses into sentences) |
               +-------------------------------------------------+
                                        |
                                        v
               +-------------------------------------------------+
               |                LocalTTSManager                  |
               +-------------------------------------------------+
                         /                              \
                        v                                v
    +----------------------------------+  +----------------------------------+
    |         PiperTTSProvider         |  |        ClonedVoiceProvider       |
    | (Fast ONNX: uk_UA, en_US, etc.)  |  |   (Zero-Shot Cloning with WAV    |
    |      RTF < 0.10 on M1 Pro        |  |         5-10s Reference)         |
    +----------------------------------+  +----------------------------------+
                        \                                /
                         +--------------+---------------+
                                        |
                            (16kHz int16 PCM Chunks)
                                        v
               +-------------------------------------------------+
               |            DualChannelAudioEngine               |
               |       (JitterBuffer + Smart Ducking DSP)        |
               +-------------------------------------------------+
                        /                                \
                       v                                  v
    +----------------------------------+  +----------------------------------+
    |         Outgoing Line            |  |         Incoming Line            |
    | (Virtual Mic -> Zoom/Meet Mic)   |  |   (Physical Headphones / Aux)    |
    +----------------------------------+  +----------------------------------+
```

---

## 3. Data Models & Interface Contracts

### 3.1. Voice Profile Model

Voice profiles allow users to choose standard built-in neural voices or create cloned voice profiles using short audio samples.

```python
# backend/tts/models.py
from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

class VoiceProfile(BaseModel):
    id: str = Field(..., description="Unique slug or UUID for the voice profile")
    name: str = Field(..., description="Display name, e.g. 'My Voice (English Cloned)'")
    language: str = Field(..., description="Target language code: 'uk', 'en', 'de', 'pl', etc.")
    engine_type: Literal["builtin", "cloned"] = Field(
        ..., description="Synthesis engine type: 'builtin' (fast ONNX) or 'cloned' (zero-shot)"
    )
    model_name: Optional[str] = Field(
        None, description="Identifier of the ONNX base model (e.g. 'uk_UA-lada-medium')"
    )
    reference_audio_path: Optional[str] = Field(
        None, description="Absolute or relative path to 5-10s WAV reference sample"
    )
    speaker_id: Optional[int] = Field(
        0, description="Optional speaker index for multi-speaker ONNX models"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )
```

### 3.2. Voice Selection Request Model

Extensions to `CallStartRequest`, `DubbingStartRequest`, and `SampleStartRequest`:

```python
# backend/models/requests.py
from pydantic import BaseModel
from typing import Literal, Optional

class VoiceSelection(BaseModel):
    mode: Literal["cloud", "local", "cloned"]
    voice_id: str  # "Puck", "uk_lada", or UUID of cloned profile

class CallStartRequest(BaseModel):
    my_mic_index: Optional[int] = None
    call_virtual_mic_index: Optional[int] = None
    call_input_index: Optional[int] = None
    headphones_index: Optional[int] = None
    partner_lang: str = "en"
    outgoing_voice: VoiceSelection
    incoming_voice: VoiceSelection
    ducking_factor: float = 0.2
    jitter_buffer_ms: int = 75
    api_key: Optional[str] = None
```

### 3.3. TTS Provider Contract

```python
# backend/tts/base.py
from abc import ABC, abstractmethod
from typing import AsyncGenerator
import numpy as np
from .models import VoiceProfile

class BaseTTSProvider(ABC):
    """Abstract interface for local speech synthesis providers."""

    @abstractmethod
    async def synthesize(self, text: str, profile: VoiceProfile) -> np.ndarray:
        """Synthesize a complete phrase into a 16kHz int16 numpy array."""
        pass

    @abstractmethod
    async def synthesize_stream(
        self, text: str, profile: VoiceProfile
    ) -> AsyncGenerator[np.ndarray, None]:
        """Stream synthesized 16kHz int16 PCM chunks for low-latency playback."""
        pass
```

---

## 4. Component Details & Pipeline Execution

### 4.1. Sentence & Punctuation Streamer (`PunctuationSentenceStreamer`)

To prevent robotic single-word synthesis while avoiding multi-second delays waiting for complete turns:
1. **Token Ingestion:** Collects incoming streaming tokens from Gemini Live output events.
2. **Punctuation Boundaries:** Detects syntagm / clause boundaries using regular expressions (`[.,!?;:]|\n`).
3. **Timeout Flushing:** If no new tokens are received for 450 ms and the buffer holds >= 3 words, the accumulated text is immediately sent to synthesis.
4. **Cancellation / Interruption:** When the speaker interrupts or the session stops, the buffer immediately clears pending tokens and cancels active synthesis tasks.

### 4.2. Piper TTS ONNX Provider (`PiperTTSProvider`)

* **Runtime:** Uses `onnxruntime` with Apple Silicon CoreML / CPU acceleration.
* **Pre-bundled / Downloadable Models:**
  - Ukrainian: `uk_UA-lada-medium` (Natural, clean Ukrainian intonation)
  - English: `en_US-lessac-medium` / `en_US-ryan-medium`
* **Performance:** Real-Time Factor (RTF) < 0.10 on M1 Pro. Generating a 2-second audio segment takes ~120 ms.
* **Audio Resampling:** If the model outputs 22.05 kHz or 24 kHz, it is resampled to 16 kHz using linear interpolation or fast scipy resampler before insertion into `DualChannelAudioEngine`.

### 4.3. Voice Cloning Provider (`ClonedVoiceProvider`)

* **Audio Reference Ingestion:** Accepts 5–10 seconds of clean speech (16 kHz WAV, mono).
* **Speaker Latent Extraction:** Computes speaker embedding vector once when the profile is configured, caching the embedding on disk and in memory.
* **Conditioned Synthesis:** Synthesizes the target translation conditioned on the speaker embedding, matching the original timbre and pitch contour.

---

## 5. REST Endpoints & Storage Layout

### 5.1. File System Storage Layout

```text
backend/
├── data/
│   ├── voice_profiles.json          # Persisted profile metadata
│   └── samples/                     # Stored WAV reference files for cloning
│       ├── sample_my_voice.wav
│       └── sample_partner.wav
└── models/
    └── piper/                       # Local ONNX weights & voice configs
        ├── uk_UA-lada-medium.onnx
        ├── uk_UA-lada-medium.onnx.json
        ├── en_US-lessac-medium.onnx
        └── en_US-lessac-medium.onnx.json
```

### 5.2. API Endpoints

1. `GET /api/voices/options`
   Returns categorized voice choices:
   - `cloud`: Prebuilt Gemini voices (`Puck`, `Aoede`, etc.)
   - `builtin`: Fast local ONNX voices (`uk_lada`, `en_lessac`)
   - `cloned`: User-created voice cloning profiles
2. `GET /api/voice-profiles`
   Retrieves all saved custom profiles.
3. `POST /api/voice-profiles`
   Creates a new voice profile (JSON payload: name, language, engine_type).
4. `POST /api/voice-profiles/{profile_id}/upload-sample`
   Uploads a WAV/MP3 file for voice cloning; normalizes audio to 16 kHz 16-bit mono.
5. `POST /api/voice-profiles/{profile_id}/record-sample`
   Captures 5–10 seconds directly from the chosen microphone input.
6. `POST /api/voice-profiles/test-synthesize`
   Synthesizes a short test sentence so the user can preview the voice prior to calls.
7. `DELETE /api/voice-profiles/{profile_id}`
   Deletes the profile metadata and its corresponding audio samples.

---

## 6. Frontend UI / UX Architecture

### 6.1. Domain-Driven Components

```text
src/
├── components/
│   ├── voices/
│   │   ├── VoiceSelector.tsx        # Grouped dropdown (Cloud, Local, Cloned)
│   │   ├── VoiceProfileModal.tsx    # Modal for creating & recording voice clones
│   │   ├── AudioRecorderWidget.tsx  # Interactive 5-10s audio recorder with VU meter
│   │   └── VoicePreviewPlayer.tsx   # Quick audio preview player
│   ├── CallView.tsx                 # Uses VoiceSelector for Outgoing & Incoming
│   ├── DubbingView.tsx              # Uses VoiceSelector for Target Dubbing Voice
│   └── TestingView.tsx              # Uses VoiceSelector for Sample & Mic Playground
├── types/
│   └── voice.ts                     # Strict TypeScript interfaces for profiles & modes
└── hooks/
    └── useVoiceProfiles.ts          # SWR / state hook for profile CRUD and previews
```

### 6.2. User Experience Flow for Cloning

1. User clicks **"+ Новий голосовий профіль / Клонування"** beside the voice selector.
2. `VoiceProfileModal` opens:
   - User enters profile name ("Мій голос (Zoom)").
   - User clicks **"Записати голос"** and speaks a 5–10 second test sentence into their microphone.
   - Or user drags & drops a clear `.wav` / `.mp3` sample.
3. User clicks **"Прослухати тест"** to verify synthesis quality.
4. User clicks **"Зберегти профіль"**. The new profile is immediately available in both Outgoing and Incoming line selectors.

---

## 7. Error Handling, Fallback & Performance Guardrails

1. **Graceful Fallback:**
   If a local ONNX model or cloning reference fails to load, the session logs a warning and falls back to the default built-in voice or Gemini Cloud audio without terminating the live call.
2. **Audio Sample Normalization:**
   Uploaded or recorded reference audio is validated: duration between 3s and 30s, RMS power threshold check (to avoid silent or noisy recordings), and converted to 16 kHz mono WAV.
3. **Turn Interruption Management:**
   When an incoming speech interruption event is detected (`on_interrupt`), active sentence streamer queues and TTS synthesis tasks are aborted within < 10 ms to prevent audio buffer pollution.
4. **Memory Footprint:**
   Local ONNX runtime models consume < 150 MB of unified memory on Apple M1 Pro, avoiding CPU/GPU contention with video conferencing tools.

---

## 8. Verification & Testing Strategy

1. **Unit Testing:**
   - `test_punctuation_streamer.py`: Boundary conditions, punctuation splitting, sentence joining, timeout flush.
   - `test_voice_profiles_crud.py`: JSON profile persistence, audio file validation, deletion cleanup.
   - `test_tts_provider.py`: Verification of generated PCM shape, sample rate (16 kHz), and non-zero amplitude.
2. **Integration Testing:**
   - Verification of `POST /call/start` with `VoiceSelection(mode="local", voice_id="uk_lada")`.
   - Telemetry check: ensuring `outgoing_volume_db` and `incoming_volume_db` properly reflect local TTS audio.
3. **Manual Playground Verification:**
   - In `TestingView`, running the IT Standup and System Architecture samples using both Piper Local Voice and Cloned Voice profiles.
