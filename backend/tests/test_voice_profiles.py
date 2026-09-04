from __future__ import annotations

import io
from pathlib import Path
import wave
import numpy as np
import pytest

from tts.models import VoiceProfile
from tts.profile_storage import VoiceProfileStorage


def make_test_wav(
    duration_sec: float,
    sample_rate: int = 16000,
    channels: int = 1,
    frequency: float = 440.0,
) -> bytes:
    """Generate synthetic in-memory WAV audio bytes for testing."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        num_samples = int(duration_sec * sample_rate)
        t = np.linspace(0, duration_sec, num_samples, endpoint=False)
        signal = (np.sin(2 * np.pi * frequency * t) * 12000.0).astype(np.int16)
        if channels > 1:
            multi = np.repeat(signal[:, np.newaxis], channels, axis=1).flatten()
            wf.writeframes(multi.tobytes())
        else:
            wf.writeframes(signal.tobytes())
    return buf.getvalue()


def test_default_builtin_profiles(tmp_path: Path):
    """Verify built-in profiles are prepopulated on initialization."""
    storage = VoiceProfileStorage(data_dir=tmp_path)

    profiles = storage.list_profiles()
    ids = {p.id for p in profiles}

    assert "uk_lada" in ids
    assert "en_lessac" in ids

    uk_profile = storage.get_profile("uk_lada")
    assert uk_profile is not None
    assert uk_profile.language == "uk"
    assert uk_profile.engine_type == "builtin"
    assert uk_profile.model_name == "uk_UA-lada-medium"

    en_profile = storage.get_profile("en_lessac")
    assert en_profile is not None
    assert en_profile.language == "en"
    assert en_profile.engine_type == "builtin"
    assert en_profile.model_name == "en_US-lessac-medium"

    # Protected from deletion
    with pytest.raises(ValueError, match="Cannot delete built-in"):
        storage.delete_profile("uk_lada")


def test_crud_operations(tmp_path: Path):
    """Verify profile creation, retrieval, filtering, and deletion."""
    storage = VoiceProfileStorage(data_dir=tmp_path)

    new_profile = VoiceProfile(
        id="custom_voice_1",
        name="Мій Клонований Голос",
        language="uk",
        engine_type="cloned",
        reference_audio_path=None,
    )

    created = storage.create_profile(new_profile)
    assert created.id == "custom_voice_1"

    # Retrieval
    retrieved = storage.get_profile("custom_voice_1")
    assert retrieved is not None
    assert retrieved.name == "Мій Клонований Голос"

    # Filtering by language
    uk_voices = storage.list_profiles(language="uk")
    assert any(p.id == "custom_voice_1" for p in uk_voices)

    en_voices = storage.list_profiles(language="en")
    assert not any(p.id == "custom_voice_1" for p in en_voices)

    # Deletion
    deleted = storage.delete_profile("custom_voice_1")
    assert deleted is True
    assert storage.get_profile("custom_voice_1") is None

    # Deleting non-existent profile
    assert storage.delete_profile("non_existent_id") is False


def test_audio_normalization_and_sample_saving(tmp_path: Path):
    """Verify audio sample normalization: 22.05kHz stereo -> 16kHz mono 16-bit WAV."""
    storage = VoiceProfileStorage(data_dir=tmp_path)

    profile = VoiceProfile(
        id="clone_norm_test",
        name="Тест Нормалізації",
        language="uk",
        engine_type="cloned",
    )
    storage.create_profile(profile)

    # Generate 5.0 seconds of 22050 Hz stereo audio
    wav_bytes = make_test_wav(duration_sec=5.0, sample_rate=22050, channels=2)

    saved_path_str = storage.save_sample("clone_norm_test", wav_bytes)
    saved_path = Path(saved_path_str)
    assert saved_path.exists()

    # Inspect normalized file
    with wave.open(str(saved_path), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        duration = float(wf.getnframes()) / float(wf.getframerate())
        assert pytest.approx(duration, abs=0.1) == 5.0

    # Verify profile was updated with sample path
    updated_profile = storage.get_profile("clone_norm_test")
    assert updated_profile is not None
    assert updated_profile.reference_audio_path == str(saved_path)

    # Deleting profile cleans up sample file
    storage.delete_profile("clone_norm_test")
    assert not saved_path.exists()


def test_audio_validation_duration_limits(tmp_path: Path):
    """Verify sample duration guardrails (3 to 30 seconds)."""
    storage = VoiceProfileStorage(data_dir=tmp_path)

    profile = VoiceProfile(
        id="limits_test",
        name="Limits Test",
        language="en",
        engine_type="cloned",
    )
    storage.create_profile(profile)

    # Too short (< 3.0s)
    short_wav = make_test_wav(duration_sec=2.5)
    with pytest.raises(ValueError, match="outside allowed range"):
        storage.save_sample("limits_test", short_wav)

    # Too long (> 30.0s)
    long_wav = make_test_wav(duration_sec=32.0)
    with pytest.raises(ValueError, match="outside allowed range"):
        storage.save_sample("limits_test", long_wav)

    # Corrupt data
    with pytest.raises(ValueError, match="too small"):
        storage.save_sample("limits_test", b"short_corrupt")
