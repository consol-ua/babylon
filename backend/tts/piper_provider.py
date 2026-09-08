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

try:
    from piper.voice import PiperVoice
    from piper.config import SynthesisConfig
except ImportError:
    PiperVoice = None
    SynthesisConfig = None

from .base import BaseTTSProvider
from .models import VoiceProfile
from .normalizer import normalize_ukrainian_text

logger = logging.getLogger("piper_tts_provider")


class PiperTTSProvider(BaseTTSProvider):
    """
    Piper TTS Provider executing local ONNX voice models with onnxruntime and piper-tts.
    Includes macOS native speech and acoustic synthesis fallbacks for missing model environments.
    """

    def __init__(self, models_dir: Optional[Union[str, Path]] = None) -> None:
        if models_dir is None:
            self.models_dir = Path(__file__).parent.parent / "models" / "piper"
        else:
            self.models_dir = Path(models_dir)

        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: Dict[str, ort.InferenceSession] = {}
        self._configs: Dict[str, dict] = {}
        self._piper_voices: Dict[str, PiperVoice] = {}


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

    def _load_piper_voice(self, model_name: str) -> Optional[PiperVoice]:
        """Load or retrieve cached PiperVoice instance for neural synthesis."""
        if PiperVoice is None:
            return None

        if model_name in self._piper_voices:
            return self._piper_voices[model_name]

        onnx_path, config_path = self._get_model_paths(model_name)
        if not onnx_path.exists() or not config_path.exists():
            return None

        try:
            voice = PiperVoice.load(str(onnx_path), str(config_path))
            self._piper_voices[model_name] = voice
            logger.info("Loaded Piper neural voice instance for model: %s", model_name)
            return voice
        except Exception as err:
            logger.warning("Failed loading PiperVoice instance for %s: %s", model_name, err)
            return None

    def _synthesize_macos_say(self, text: str, language: str) -> Optional[np.ndarray]:
        """
        Synthesize speech using macOS native 'say' command to 16kHz mono WAV.
        Provides zero-latency, high quality natural speech fallback.
        """
        import platform
        import shutil
        import subprocess
        import tempfile
        import wave

        if platform.system() != "Darwin" or not shutil.which("say"):
            return None

        clean_text = text.strip()
        if not clean_text:
            return np.zeros(0, dtype=np.int16)

        # Lesya for Ukrainian, Samantha for English / others
        voice = "Lesya" if language.lower() == "uk" else "Samantha"

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            cmd = ["say", "-v", voice, "-o", tmp_path, "--data-format=LEI16@16000", clean_text]
            res = subprocess.run(cmd, capture_output=True, timeout=5.0)
            if res.returncode != 0 or not Path(tmp_path).exists():
                return None

            with wave.open(tmp_path, "rb") as wf:
                nframes = wf.getnframes()
                raw_bytes = wf.readframes(nframes)
                samples = np.frombuffer(raw_bytes, dtype=np.int16)
                return samples
        except Exception as e:
            logger.warning("macOS say fallback failed: %s", e)
            return None
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass

    async def synthesize(self, text: str, profile: VoiceProfile) -> np.ndarray:
        """
        Synthesize text into a 16kHz int16 mono PCM numpy array using:
        1. Local Piper ONNX neural voice (if available)
        2. macOS native speech synthesis ('say' with Lesya/Samantha)
        3. Acoustic harmonic fallback (for headless CI testing)
        """
        clean_text = text.strip()
        if not clean_text:
            return np.zeros(0, dtype=np.int16)

        model_name = profile.model_name or ("uk_UA-lada-medium" if profile.language == "uk" else "en_US-lessac-medium")

        # 1. Primary: Neural Piper ONNX synthesis
        voice = self._load_piper_voice(model_name)
        if voice is not None:
            try:
                if profile.language == "uk" or "lada" in (profile.model_name or ""):
                    txt_input = normalize_ukrainian_text(clean_text)
                else:
                    txt_input = clean_text

                if not txt_input:
                    return np.zeros(0, dtype=np.int16)

                syn_cfg = None
                if profile.speaker_id is not None and SynthesisConfig is not None:
                    syn_cfg = SynthesisConfig(speaker_id=profile.speaker_id)

                chunks = list(voice.synthesize(txt_input, syn_config=syn_cfg))
                if chunks:
                    raw_int16 = np.concatenate([c.audio_int16_array for c in chunks])
                    # Verify output audio contains real voice signal and not degenerate silence
                    if len(raw_int16) > 0 and np.max(np.abs(raw_int16)) > 50:
                        sr = chunks[0].sample_rate
                        return self._resample_audio(raw_int16, sr)
                    else:
                        logger.warning("Piper produced near-silent audio for '%s', trying fallback.", txt_input)
            except Exception as err:
                logger.warning("Piper neural synthesis failed for %s: %s", model_name, err)

        # 2. High-quality offline fallback: macOS native speech synthesis
        macos_audio = self._synthesize_macos_say(clean_text, profile.language)
        if macos_audio is not None and len(macos_audio) > 0:
            return macos_audio

        # 3. Clean acoustic fallback (for mock unit tests)
        logger.info("Using acoustic synthesis fallback for profile '%s'.", profile.id)
        return self._generate_acoustic_fallback(clean_text, profile)

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
