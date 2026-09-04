from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator
import numpy as np

from .models import VoiceProfile


class BaseTTSProvider(ABC):
    """Abstract interface for speech synthesis providers producing 16kHz int16 mono PCM."""

    SAMPLE_RATE: int = 16000

    @abstractmethod
    async def synthesize(self, text: str, profile: VoiceProfile) -> np.ndarray:
        """
        Synthesize a complete phrase into a 16kHz int16 mono PCM numpy array.

        Args:
            text: Input text string to synthesize.
            profile: Target voice profile configuration.

        Returns:
            1D numpy array of dtype np.int16 containing 16kHz mono audio.
        """
        pass

    @abstractmethod
    async def synthesize_stream(
        self, text: str, profile: VoiceProfile
    ) -> AsyncGenerator[np.ndarray, None]:
        """
        Stream synthesized 16kHz int16 mono PCM chunks for low-latency playback.

        Args:
            text: Input text string to synthesize.
            profile: Target voice profile configuration.

        Yields:
            Sequential 1D numpy arrays of dtype np.int16 containing 16kHz mono audio chunks.
        """
        pass

    @staticmethod
    def ensure_pcm16_mono(audio: np.ndarray) -> np.ndarray:
        """
        Ensure audio array is 1D np.int16 PCM.

        Args:
            audio: Input numpy array.

        Returns:
            Normalized 1D np.int16 array.
        """
        if not isinstance(audio, np.ndarray):
            raise TypeError(f"Expected np.ndarray, got {type(audio).__name__}")
        if audio.ndim > 1:
            audio = audio.flatten()
        if audio.dtype != np.int16:
            if np.issubdtype(audio.dtype, np.floating):
                # Assume float in range [-1.0, 1.0] if max <= 1.0
                if np.max(np.abs(audio)) <= 1.0 and len(audio) > 0:
                    audio = (audio * 32767.0).astype(np.int16)
                else:
                    audio = np.clip(audio, -32768, 32767).astype(np.int16)
            else:
                audio = audio.astype(np.int16)
        return audio
