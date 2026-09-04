from __future__ import annotations

from pathlib import Path
import pytest
import numpy as np

from tts.models import VoiceProfile, VoiceSelection
from tts.piper_provider import PiperTTSProvider
from tts.cloned_provider import ClonedVoiceProvider
from tts.profile_storage import VoiceProfileStorage
from tts.manager import LocalTTSManager
from tests.test_voice_profiles import make_test_wav


@pytest.mark.asyncio
async def test_piper_acoustic_fallback(tmp_path: Path):
    """Verify PiperTTSProvider acoustic synthesis fallback produces valid 16kHz int16 PCM."""
    provider = PiperTTSProvider(models_dir=tmp_path / "piper_models")
    profile = VoiceProfile(
        id="uk_lada",
        name="Лада",
        language="uk",
        engine_type="builtin",
        model_name="uk_UA-lada-medium",
    )

    audio = await provider.synthesize("Доброго дня, як ваші справи?", profile)

    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.int16
    assert audio.ndim == 1
    assert len(audio) > 0
    # Verify non-zero amplitude
    assert np.max(np.abs(audio)) > 1000

    # Test streaming
    chunks = []
    async for chunk in provider.synthesize_stream("Тестове речення для потокового виводу.", profile):
        assert isinstance(chunk, np.ndarray)
        assert chunk.dtype == np.int16
        chunks.append(chunk)

    assert len(chunks) > 0
    combined = np.concatenate(chunks)
    assert len(combined) > 0


@pytest.mark.asyncio
async def test_cloned_voice_provider(tmp_path: Path):
    """Verify ClonedVoiceProvider extracts features and conditions synthesis on sample."""
    storage = VoiceProfileStorage(data_dir=tmp_path)
    profile = VoiceProfile(
        id="clone_test",
        name="Тестовий Клон",
        language="uk",
        engine_type="cloned",
    )
    storage.create_profile(profile)

    # Save 4.0s sample
    wav_bytes = make_test_wav(duration_sec=4.0, sample_rate=16000, frequency=220.0)
    sample_path = storage.save_sample("clone_test", wav_bytes)

    cloned_provider = ClonedVoiceProvider(
        embeddings_cache_dir=tmp_path / "embeddings",
    )

    updated_profile = storage.get_profile("clone_test")
    assert updated_profile is not None
    assert updated_profile.reference_audio_path == sample_path

    # Synthesize conditioned
    audio = await cloned_provider.synthesize("Привіт, це мій синтезований голос.", updated_profile)
    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.int16
    assert len(audio) > 0
    assert np.max(np.abs(audio)) > 1000


@pytest.mark.asyncio
async def test_local_tts_manager(tmp_path: Path):
    """Verify LocalTTSManager lists categorized voices and executes synthesis."""
    storage = VoiceProfileStorage(data_dir=tmp_path)
    # Add a custom cloned voice
    cloned_profile = VoiceProfile(
        id="cloned_vip",
        name="VIP Clone",
        language="uk",
        engine_type="cloned",
    )
    storage.create_profile(cloned_profile)

    manager = LocalTTSManager(storage=storage)

    # Available voices
    voices = manager.get_available_voices(language="uk")
    modes = {v.mode for v in voices}
    assert "cloud" in modes
    assert "local" in modes
    assert "cloned" in modes

    # Synthesize local
    selection_local = VoiceSelection(mode="local", voice_id="uk_lada")
    audio_local = await manager.synthesize_phrase("Привіт зі сховища!", selection_local)
    assert isinstance(audio_local, np.ndarray)
    assert audio_local.dtype == np.int16
    assert len(audio_local) > 0

    # Stream cloned
    selection_cloned = VoiceSelection(mode="cloned", voice_id="cloned_vip")
    chunks = []
    async for chunk in manager.synthesize_stream("Потоковий тест клонування.", selection_cloned):
        chunks.append(chunk)
    assert len(chunks) > 0
