import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from main import app, normalize_voice_selection
from tts.models import VoiceSelection

client = TestClient(app)

def test_normalize_voice_selection():
    # String cloud voice
    v1 = normalize_voice_selection("Puck")
    assert v1.mode == "cloud"
    assert v1.voice_id == "Puck"

    # String local voice
    v2 = normalize_voice_selection("uk_lada")
    assert v2.mode == "local"
    assert v2.voice_id == "uk_lada"

    # Dict format
    v3 = normalize_voice_selection({"mode": "cloned", "voice_id": "test_clone"})
    assert v3.mode == "cloned"
    assert v3.voice_id == "test_clone"

    # Object format
    v4 = normalize_voice_selection(VoiceSelection(mode="local", voice_id="en_lessac"))
    assert v4.mode == "local"
    assert v4.voice_id == "en_lessac"

def test_get_voices_options():
    res = client.get("/api/voices/options")
    assert res.status_code == 200
    data = res.json()
    assert "cloud" in data
    assert "local" in data
    assert "cloned" in data
    assert len(data["cloud"]) >= 5
    assert any(v["id"] == "Puck" for v in data["cloud"])

def test_voice_profiles_crud():
    # 1. List initial profiles
    res = client.get("/api/voice-profiles")
    assert res.status_code == 200
    profiles = res.json()["profiles"]
    assert len(profiles) >= 2  # default built-in profiles

    # 2. Create custom cloned profile
    create_payload = {
        "name": "Integration Test Voice",
        "language": "en",
        "engine_type": "cloned",
        "model_name": None
    }
    create_res = client.post("/api/voice-profiles", json=create_payload)
    assert create_res.status_code == 200
    created = create_res.json()
    profile_id = created["id"]
    assert created["name"] == "Integration Test Voice"

    # 3. Test synthesize
    synth_payload = {
        "text": "Hello this is a test phrase.",
        "voice_id": profile_id,
        "mode": "cloned",
        "language": "en"
    }
    synth_res = client.post("/api/voice-profiles/test-synthesize", json=synth_payload)
    assert synth_res.status_code == 200
    synth_data = synth_res.json()
    assert synth_data["status"] == "ok"
    assert "audio_base64" in synth_data

    # 4. Attempt to delete built-in profile (should fail with 400)
    del_builtin_res = client.delete("/api/voice-profiles/uk_lada")
    assert del_builtin_res.status_code == 400

    # 5. Delete custom profile (should succeed)
    del_res = client.delete(f"/api/voice-profiles/{profile_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"
