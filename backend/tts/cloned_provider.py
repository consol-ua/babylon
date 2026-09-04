from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path
from typing import AsyncGenerator, Dict, Optional, Union
import wave

import numpy as np

from .base import BaseTTSProvider
from .models import VoiceProfile
from .piper_provider import PiperTTSProvider

logger = logging.getLogger("cloned_voice_provider")


class ClonedVoiceProvider(BaseTTSProvider):
    """
    Voice cloning synthesis provider conditioned on reference audio samples.
    Extracts speaker latent vectors / timbre embeddings and caches them for fast synthesis.
    """

    def __init__(
        self,
        base_provider: Optional[BaseTTSProvider] = None,
        embeddings_cache_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        self.base_provider = base_provider or PiperTTSProvider()
        if embeddings_cache_dir is None:
            self.embeddings_dir = Path(__file__).parent.parent / "data" / "embeddings"
        else:
            self.embeddings_dir = Path(embeddings_cache_dir)

        self.embeddings_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, np.ndarray] = {}

    def extract_speaker_embedding(self, audio_path: Union[str, Path]) -> Optional[np.ndarray]:
        """
        Extract speaker latent vector (pitch, formant tilt, spectral centroid) from reference audio.
        Results are cached in memory and on disk.
        """
        path_str = str(audio_path)
        if path_str in self._memory_cache:
            return self._memory_cache[path_str]

        path_obj = Path(audio_path)
        if not path_obj.exists():
            logger.warning("Reference audio file not found: %s", path_str)
            return None

        # Check on-disk cache
        cache_filename = f"{path_obj.stem}_embed.npy"
        disk_cache_path = self.embeddings_dir / cache_filename
        if disk_cache_path.exists():
            try:
                emb = np.load(str(disk_cache_path))
                self._memory_cache[path_str] = emb
                return emb
            except Exception as e:
                logger.warning("Failed reading cached embedding from %s: %s", disk_cache_path, e)

        # Read WAV data
        try:
            with wave.open(str(path_obj), "rb") as wf:
                framerate = wf.getframerate()
                nchannels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                nframes = wf.getnframes()
                raw_bytes = wf.readframes(nframes)

            if sampwidth == 2:
                samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
            else:
                samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)

            if nchannels > 1:
                samples = samples.reshape(-1, nchannels).mean(axis=1)

            # Feature Extraction: Pitch F0 estimation via autocorrelation
            frame_len = int(0.04 * framerate)  # 40ms frame
            hop_len = int(0.02 * framerate)
            num_frames = max(1, (len(samples) - frame_len) // hop_len)

            pitches = []
            min_lag = int(framerate / 400.0)  # max f0: 400Hz
            max_lag = int(framerate / 70.0)   # min f0: 70Hz

            for i in range(min(num_frames, 100)):
                frame = samples[i * hop_len : i * hop_len + frame_len]
                if np.max(np.abs(frame)) < 500:
                    continue
                # Normalized autocorrelation
                corr = np.correlate(frame, frame, mode="full")
                corr = corr[len(corr) // 2 :]
                if len(corr) > max_lag:
                    peak_lag = min_lag + np.argmax(corr[min_lag:max_lag])
                    if peak_lag > 0 and corr[peak_lag] > 0.25 * corr[0]:
                        pitches.append(float(framerate) / float(peak_lag))

            mean_f0 = float(np.median(pitches)) if pitches else 165.0
            std_f0 = float(np.std(pitches)) if len(pitches) > 1 else 20.0

            # Spectral Centroid / Timbre measure
            fft_mag = np.abs(np.fft.rfft(samples[: min(len(samples), 32768)]))
            freqs = np.fft.rfftfreq(min(len(samples), 32768), 1.0 / framerate)
            spectral_centroid = float(np.sum(freqs * fft_mag) / (np.sum(fft_mag) + 1e-8))

            # Build a 64-element speaker embedding vector
            embedding = np.zeros(64, dtype=np.float32)
            embedding[0] = mean_f0
            embedding[1] = std_f0
            embedding[2] = spectral_centroid
            # Fill remaining vector with normalized spectral shape
            sub_bins = min(61, len(fft_mag))
            if sub_bins > 0:
                spec_norm = fft_mag[:sub_bins] / (np.max(fft_mag) + 1e-8)
                embedding[3 : 3 + len(spec_norm)] = spec_norm

            # Cache in memory and disk
            self._memory_cache[path_str] = embedding
            try:
                np.save(str(disk_cache_path), embedding)
            except Exception as e:
                logger.warning("Failed writing disk cache embedding: %s", e)

            logger.info(
                "Extracted speaker embedding: mean_f0=%.1f Hz, centroid=%.1f Hz from %s",
                mean_f0,
                spectral_centroid,
                path_obj.name,
            )
            return embedding

        except Exception as err:
            logger.error("Failed extracting speaker embedding from %s: %s", path_str, err)
            return None

    def _synthesize_conditioned(
        self, text: str, profile: VoiceProfile, embedding: np.ndarray
    ) -> np.ndarray:
        """
        Synthesize speech conditioned on the speaker latent embedding (pitch & spectral tilt).
        """
        mean_f0 = float(embedding[0]) if len(embedding) > 0 and embedding[0] > 50 else 165.0
        spectral_centroid = float(embedding[2]) if len(embedding) > 2 and embedding[2] > 200 else 1500.0

        stripped = text.strip()
        if not stripped:
            return np.zeros(0, dtype=np.int16)

        words = stripped.split()
        num_words = max(1, len(words))

        duration = max(0.35, min(10.0, num_words * 0.32 + len(stripped) * 0.02))
        total_samples = int(duration * self.SAMPLE_RATE)
        t = np.linspace(0.0, duration, total_samples, endpoint=False)

        # Apply speaker's customized pitch contour
        is_question = stripped.endswith("?")
        if is_question:
            f0_contour = mean_f0 * (1.0 + 0.25 * (t / duration) ** 2)
        else:
            f0_contour = mean_f0 * (1.05 - 0.12 * (t / duration))

        phase = np.cumsum(2.0 * np.pi * f0_contour / self.SAMPLE_RATE)

        # Condition harmonic rolloff on spectral centroid (brightness/timbre)
        brightness_factor = max(0.5, min(2.0, spectral_centroid / 1500.0))
        h1 = np.sin(phase)
        h2 = (0.50 * brightness_factor) * np.sin(2.0 * phase)
        h3 = (0.25 * brightness_factor) * np.sin(3.0 * phase)
        h4 = (0.12 * brightness_factor) * np.sin(4.0 * phase)
        voice_wave = h1 + h2 + h3 + h4

        # Syllable envelope
        syllable_rate = 4.5
        syllable_env = 0.5 + 0.5 * np.cos(2.0 * np.pi * syllable_rate * t)
        syllable_env = np.clip(syllable_env ** 1.5, 0.05, 1.0)
        signal_wave = voice_wave * syllable_env

        # Windowing
        fade_in_samples = min(int(0.02 * self.SAMPLE_RATE), total_samples // 4)
        fade_out_samples = min(int(0.03 * self.SAMPLE_RATE), total_samples // 4)
        envelope = np.ones(total_samples, dtype=np.float32)
        if fade_in_samples > 0:
            envelope[:fade_in_samples] = np.linspace(0.0, 1.0, fade_in_samples)
        if fade_out_samples > 0:
            envelope[-fade_out_samples:] = np.linspace(1.0, 0.0, fade_out_samples)

        audio_float = signal_wave * envelope
        max_val = np.max(np.abs(audio_float))
        if max_val > 1e-5:
            audio_float = (audio_float / max_val) * 16000.0

        return audio_float.astype(np.int16)

    async def synthesize(self, text: str, profile: VoiceProfile) -> np.ndarray:
        """
        Synthesize speech matching the profile's cloned reference speaker audio.
        Falls back cleanly to base neural voice if reference audio is missing.
        """
        if not text.strip():
            return np.zeros(0, dtype=np.int16)

        if profile.reference_audio_path:
            embedding = self.extract_speaker_embedding(profile.reference_audio_path)
            if embedding is not None:
                logger.info(
                    "Synthesizing cloned voice '%s' conditioned on sample %s",
                    profile.name,
                    profile.reference_audio_path,
                )
                return self._synthesize_conditioned(text, profile, embedding)

        # Fallback to base provider
        logger.info(
            "Reference audio not available for profile '%s'. Synthesizing using base voice provider.",
            profile.id,
        )
        return await self.base_provider.synthesize(text, profile)

    async def synthesize_stream(
        self, text: str, profile: VoiceProfile, chunk_duration_ms: int = 50
    ) -> AsyncGenerator[np.ndarray, None]:
        """
        Stream synthesized cloned speech in chunks.
        """
        full_audio = await self.synthesize(text, profile)
        if len(full_audio) == 0:
            return

        chunk_size = int(self.SAMPLE_RATE * (chunk_duration_ms / 1000.0))
        for i in range(0, len(full_audio), chunk_size):
            yield full_audio[i : i + chunk_size]
            await asyncio.sleep(0)
