from __future__ import annotations

import io
import json
import logging
import math
from pathlib import Path
from typing import Dict, List, Optional, Union
import wave

import numpy as np

try:
    from scipy import signal
except ImportError:
    signal = None

from .models import VoiceProfile

logger = logging.getLogger("voice_profile_storage")


class VoiceProfileStorage:
    """
    Persistent JSON-backed storage and sample manager for voice profiles.
    Prepopulates built-in Piper profiles and manages reference sample normalization.
    """

    DEFAULT_PROFILES: List[VoiceProfile] = [
        VoiceProfile(
            id="uk_lada",
            name="Лада (Швидкий UK)",
            language="uk",
            engine_type="builtin",
            model_name="uk_UA-lada-medium",
            description="Швидкий природний український голос Piper ONNX",
        ),
        VoiceProfile(
            id="en_lessac",
            name="Lessac (Natural EN)",
            language="en",
            engine_type="builtin",
            model_name="en_US-lessac-medium",
            description="Clean American English Piper ONNX voice",
        ),
    ]

    def __init__(self, data_dir: Optional[Union[str, Path]] = None) -> None:
        if data_dir is None:
            self.data_dir = Path(__file__).parent.parent / "data"
        else:
            self.data_dir = Path(data_dir)

        self.samples_dir = self.data_dir / "samples"
        self.profiles_file = self.data_dir / "voice_profiles.json"

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.samples_dir.mkdir(parents=True, exist_ok=True)

        self._profiles: Dict[str, VoiceProfile] = {}
        self._load_profiles()

    def _load_profiles(self) -> None:
        """Load profiles from JSON file or initialize with built-in defaults."""
        if self.profiles_file.exists():
            try:
                with open(self.profiles_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                loaded_profiles = {}
                for item in data:
                    try:
                        p = VoiceProfile.model_validate(item)
                        loaded_profiles[p.id] = p
                    except Exception as err:
                        logger.warning("Failed parsing profile item %s: %s", item, err)
                self._profiles = loaded_profiles
            except Exception as err:
                logger.error("Error reading %s: %s. Using defaults.", self.profiles_file, err)
                self._profiles = {}

        # Ensure default built-in profiles are present
        updated = False
        for default_p in self.DEFAULT_PROFILES:
            if default_p.id not in self._profiles:
                self._profiles[default_p.id] = default_p
                updated = True

        if updated or not self.profiles_file.exists():
            self._save_profiles()

    def _save_profiles(self) -> None:
        """Persist current profiles dictionary to JSON file."""
        try:
            data = [p.model_dump() for p in self._profiles.values()]
            with open(self.profiles_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as err:
            logger.error("Failed saving voice profiles to %s: %s", self.profiles_file, err)
            raise

    def list_profiles(self, language: Optional[str] = None) -> List[VoiceProfile]:
        """
        List all saved profiles, optionally filtered by language code.
        """
        profiles = list(self._profiles.values())
        if language is not None:
            profiles = [p for p in profiles if p.language.lower() == language.lower()]
        return profiles

    def get_profile(self, profile_id: str) -> Optional[VoiceProfile]:
        """Retrieve profile by its unique ID."""
        return self._profiles.get(profile_id)

    def create_profile(self, profile: VoiceProfile) -> VoiceProfile:
        """
        Create and persist a new voice profile.
        """
        self._profiles[profile.id] = profile
        self._save_profiles()
        logger.info("Created voice profile: id=%s name='%s'", profile.id, profile.name)
        return profile

    def delete_profile(self, profile_id: str, allow_builtin: bool = False) -> bool:
        """
        Delete a voice profile and its associated audio sample if present.
        Built-in profiles are protected from deletion by default.
        """
        if profile_id not in self._profiles:
            return False

        profile = self._profiles[profile_id]
        if profile.engine_type == "builtin" and not allow_builtin:
            raise ValueError(f"Cannot delete built-in voice profile '{profile_id}'")

        # Cleanup audio sample if existing
        if profile.reference_audio_path:
            sample_file = Path(profile.reference_audio_path)
            if sample_file.exists():
                try:
                    sample_file.unlink()
                    logger.info("Removed sample file %s for profile %s", sample_file, profile_id)
                except Exception as err:
                    logger.warning("Failed deleting sample file %s: %s", sample_file, err)

        del self._profiles[profile_id]
        self._save_profiles()
        logger.info("Deleted voice profile: id=%s", profile_id)
        return True

    def save_sample(
        self,
        profile_id: str,
        audio_bytes: bytes,
        filename: str = "sample.wav",
    ) -> str:
        """
        Validate audio duration (3s to 30s), normalize to 16kHz mono 16-bit WAV,
        save to disk, and link to profile.
        """
        profile = self.get_profile(profile_id)
        if profile is None:
            raise KeyError(f"Voice profile '{profile_id}' not found.")

        samples_pcm, orig_sr = self._parse_and_validate_audio(audio_bytes)

        # Normalize to 16kHz mono 16-bit
        if orig_sr != 16000:
            if signal is not None:
                gcd = math.gcd(16000, orig_sr)
                up = 16000 // gcd
                down = orig_sr // gcd
                resampled = signal.resample_poly(samples_pcm.astype(np.float32), up, down)
                samples_pcm = np.clip(resampled, -32768, 32767).astype(np.int16)
            else:
                target_len = int(len(samples_pcm) * 16000 / orig_sr)
                indices = np.linspace(0, len(samples_pcm) - 1, target_len)
                interp = np.interp(indices, np.arange(len(samples_pcm)), samples_pcm)
                samples_pcm = np.clip(interp, -32768, 32767).astype(np.int16)

        # Save to samples directory
        target_path = self.samples_dir / f"sample_{profile_id}.wav"
        with wave.open(str(target_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(samples_pcm.tobytes())

        profile.reference_audio_path = str(target_path)
        self._save_profiles()
        logger.info(
            "Saved and normalized reference sample for profile '%s' at %s",
            profile_id,
            target_path,
        )
        return str(target_path)

    def _parse_and_validate_audio(self, audio_bytes: bytes) -> tuple[np.ndarray, int]:
        """
        Parse WAV container or raw PCM, validate duration between 3.0s and 30.0s,
        and convert to 1D mono int16 array.
        """
        if len(audio_bytes) < 44:
            raise ValueError("Audio data is too small to be a valid audio file.")

        if audio_bytes[:4] == b"RIFF":
            try:
                with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                    channels = wf.getnchannels()
                    sampwidth = wf.getsampwidth()
                    framerate = wf.getframerate()
                    nframes = wf.getnframes()
                    raw_frames = wf.readframes(nframes)

                duration = float(nframes) / float(framerate) if framerate > 0 else 0.0
                if duration < 3.0 or duration > 30.0:
                    raise ValueError(
                        f"Audio duration {duration:.2f}s is outside allowed range (3.0 to 30.0s)"
                    )

                if sampwidth == 2:
                    samples = np.frombuffer(raw_frames, dtype=np.int16)
                elif sampwidth == 1:
                    samples = (
                        (np.frombuffer(raw_frames, dtype=np.uint8).astype(np.float32) - 128.0)
                        * 256.0
                    ).astype(np.int16)
                elif sampwidth == 4:
                    # Could be int32 or float32; check first sample
                    try:
                        f_samples = np.frombuffer(raw_frames, dtype=np.float32)
                        if np.max(np.abs(f_samples)) <= 1.05:
                            samples = np.clip(f_samples * 32767.0, -32768, 32767).astype(np.int16)
                        else:
                            samples = (np.frombuffer(raw_frames, dtype=np.int32) >> 16).astype(np.int16)
                    except Exception:
                        samples = (np.frombuffer(raw_frames, dtype=np.int32) >> 16).astype(np.int16)
                else:
                    samples = np.frombuffer(raw_frames, dtype=np.int16)

                if channels > 1:
                    samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)

                return samples, framerate

            except ValueError:
                raise
            except Exception as err:
                raise ValueError(f"Invalid WAV audio data: {err}") from err
        else:
            # Assume 16kHz 16-bit mono raw PCM
            samples = np.frombuffer(audio_bytes, dtype=np.int16)
            duration = float(len(samples)) / 16000.0
            if duration < 3.0 or duration > 30.0:
                raise ValueError(
                    f"Audio duration {duration:.2f}s is outside allowed range (3.0 to 30.0s)"
                )
            return samples, 16000
