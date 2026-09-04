from __future__ import annotations

import asyncio
import json
import logging
import math
from pathlib import Path
from typing import AsyncGenerator, Dict, Optional, Union

import numpy as np

try:
    import onnxruntime as ort
except ImportError:
    ort = None

try:
    from scipy import signal
except ImportError:
    signal = None

from .base import BaseTTSProvider
from .models import VoiceProfile

logger = logging.getLogger("piper_tts_provider")


class PiperTTSProvider(BaseTTSProvider):
    """
    Piper TTS Provider executing local ONNX voice models with onnxruntime.
    Includes acoustic synthesis fallback for testing and missing model environments.
    """

    def __init__(self, models_dir: Optional[Union[str, Path]] = None) -> None:
        if models_dir is None:
            self.models_dir = Path(__file__).parent.parent / "models" / "piper"
        else:
            self.models_dir = Path(models_dir)

        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: Dict[str, ort.InferenceSession] = {}
        self._configs: Dict[str, dict] = {}

    def _get_model_paths(self, model_name: str) -> tuple[Path, Path]:
        """Resolve .onnx and .onnx.json file paths."""
        onnx_file = self.models_dir / f"{model_name}.onnx"
        json_file = self.models_dir / f"{model_name}.onnx.json"
        return onnx_file, json_file

    def _load_session(self, model_name: str) -> Optional[tuple[ort.InferenceSession, dict]]:
        """Load or retrieve cached onnxruntime session and model config."""
        if ort is None:
            logger.warning("onnxruntime is not installed. Falling back to acoustic synthesis.")
            return None

        onnx_path, config_path = self._get_model_paths(model_name)
        if not onnx_path.exists():
            logger.info(
                "Piper ONNX model '%s' not found at %s. Using acoustic synthesis fallback.",
                model_name,
                onnx_path,
            )
            return None

        if model_name in self._sessions and model_name in self._configs:
            return self._sessions[model_name], self._configs[model_name]

        try:
            available_providers = ort.get_available_providers()
            providers = [p for p in ["CoreMLExecutionProvider", "CPUExecutionProvider"] if p in available_providers]
            if not providers:
                providers = ["CPUExecutionProvider"]

            session = ort.InferenceSession(str(onnx_path), providers=providers)
            config: dict = {}
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

            self._sessions[model_name] = session
            self._configs[model_name] = config
            logger.info("Loaded Piper ONNX voice session for model: %s", model_name)
            return session, config
        except Exception as err:
            logger.warning(
                "Failed to initialize ONNX session for %s: %s. Using fallback.",
                model_name,
                err,
            )
            return None

    def _generate_acoustic_fallback(self, text: str, profile: VoiceProfile) -> np.ndarray:
        """
        Generate a lightweight harmonic speech envelope fallback in 16kHz int16.
        Simulates natural speech cadence, pitch contour, and vocal tract formants.
        """
        stripped = text.strip()
        if not stripped:
            return np.zeros(0, dtype=np.int16)

        words = stripped.split()
        num_words = max(1, len(words))

        # Timing: ~250ms - 350ms per word with minimum 300ms duration
        total_duration = max(0.35, min(10.0, num_words * 0.32 + len(stripped) * 0.02))
        total_samples = int(total_duration * self.SAMPLE_RATE)
        t = np.linspace(0.0, total_duration, total_samples, endpoint=False)

        # Base pitch selection by voice/language profile
        if profile.language == "uk" or "lada" in (profile.model_name or ""):
            base_f0 = 220.0  # Lada (female vocal pitch)
        else:
            base_f0 = 145.0  # Lessac (neutral / masculine vocal pitch)

        # Intonation contour (pitch declination across sentence, rising for questions)
        is_question = stripped.endswith("?")
        if is_question:
            f0_contour = base_f0 * (1.0 + 0.25 * (t / total_duration) ** 2)
        else:
            f0_contour = base_f0 * (1.05 - 0.15 * (t / total_duration))

        phase = np.cumsum(2.0 * np.pi * f0_contour / self.SAMPLE_RATE)

        # Harmonic series with formant-like spectral rolloff
        h1 = np.sin(phase)
        h2 = 0.50 * np.sin(2.0 * phase)
        h3 = 0.25 * np.sin(3.0 * phase)
        h4 = 0.12 * np.sin(4.0 * phase)
        voice_wave = h1 + h2 + h3 + h4

        # Syllable envelope modulation (~4.5 Hz pseudo-syllabic rate)
        syllable_rate = 4.5
        syllable_env = 0.5 + 0.5 * np.cos(2.0 * np.pi * syllable_rate * t)
        syllable_env = np.clip(syllable_env ** 1.5, 0.05, 1.0)

        # Word boundary dips
        signal_wave = voice_wave * syllable_env

        # Smooth attack (20ms) and decay (30ms) window to prevent clicks
        fade_in_samples = min(int(0.02 * self.SAMPLE_RATE), total_samples // 4)
        fade_out_samples = min(int(0.03 * self.SAMPLE_RATE), total_samples // 4)
        envelope = np.ones(total_samples, dtype=np.float32)
        if fade_in_samples > 0:
            envelope[:fade_in_samples] = np.linspace(0.0, 1.0, fade_in_samples)
        if fade_out_samples > 0:
            envelope[-fade_out_samples:] = np.linspace(1.0, 0.0, fade_out_samples)

        audio_float = signal_wave * envelope
        # Peak normalization to ~16000 amplitude
        max_val = np.max(np.abs(audio_float))
        if max_val > 1e-5:
            audio_float = (audio_float / max_val) * 16000.0

        return audio_float.astype(np.int16)

    def _resample_audio(self, audio: np.ndarray, orig_sr: int) -> np.ndarray:
        """Resample audio array to 16kHz int16 mono."""
        if orig_sr == self.SAMPLE_RATE:
            return self.ensure_pcm16_mono(audio)

        if signal is not None:
            gcd = math.gcd(self.SAMPLE_RATE, orig_sr)
            up = self.SAMPLE_RATE // gcd
            down = orig_sr // gcd
            resampled = signal.resample_poly(audio.astype(np.float32), up, down)
            return self.ensure_pcm16_mono(resampled)
        else:
            # Fallback linear interpolation if scipy signal is unavailable
            num_output_samples = int(len(audio) * self.SAMPLE_RATE / orig_sr)
            indices = np.linspace(0, len(audio) - 1, num_output_samples)
            interpolated = np.interp(indices, np.arange(len(audio)), audio)
            return self.ensure_pcm16_mono(interpolated)

    async def synthesize(self, text: str, profile: VoiceProfile) -> np.ndarray:
        """
        Synthesize text into a 16kHz int16 mono PCM numpy array using Piper ONNX or fallback.
        """
        if not text.strip():
            return np.zeros(0, dtype=np.int16)

        model_name = profile.model_name or "uk_UA-lada-medium"
        loaded = self._load_session(model_name)

        if loaded is None:
            # Clean fallback with clear logging
            logger.info("Using acoustic synthesis fallback for profile '%s'.", profile.id)
            return self._generate_acoustic_fallback(text, profile)

        session, config = loaded
        try:
            audio_sample_rate = config.get("audio", {}).get("sample_rate", 22050)
            phoneme_id_map = config.get("phoneme_id_map", {})

            # Prepare basic character/phoneme token IDs
            tokens = [phoneme_id_map.get(ch, [0])[0] if isinstance(phoneme_id_map.get(ch), list)
                      else phoneme_id_map.get(ch, 0) for ch in text.lower()]
            if not tokens:
                tokens = [0]

            phoneme_ids = np.array([tokens], dtype=np.int64)
            phoneme_lengths = np.array([phoneme_ids.shape[1]], dtype=np.int64)
            scales = np.array([0.667, 1.0, 0.8], dtype=np.float32)

            inputs: dict = {
                "input": phoneme_ids,
                "input_lengths": phoneme_lengths,
                "scales": scales,
            }

            input_names = [inp.name for inp in session.get_inputs()]
            if "sid" in input_names:
                speaker_id = profile.speaker_id if profile.speaker_id is not None else 0
                inputs["sid"] = np.array([speaker_id], dtype=np.int64)

            outputs = session.run(None, inputs)
            raw_audio = outputs[0].flatten()

            resampled = self._resample_audio(raw_audio, audio_sample_rate)
            return resampled

        except Exception as err:
            logger.warning(
                "Inference failed for Piper model %s: %s. Falling back to acoustic synthesis.",
                model_name,
                err,
            )
            return self._generate_acoustic_fallback(text, profile)

    async def synthesize_stream(
        self, text: str, profile: VoiceProfile, chunk_duration_ms: int = 50
    ) -> AsyncGenerator[np.ndarray, None]:
        """
        Stream synthesized 16kHz int16 PCM in chunks.
        """
        full_audio = await self.synthesize(text, profile)
        if len(full_audio) == 0:
            return

        chunk_size = int(self.SAMPLE_RATE * (chunk_duration_ms / 1000.0))
        for i in range(0, len(full_audio), chunk_size):
            yield full_audio[i : i + chunk_size]
            await asyncio.sleep(0)
