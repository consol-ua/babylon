from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field


class VoiceProfile(BaseModel):
    """Profile representation for local built-in and cloned neural voices."""

    id: str = Field(..., description="Unique slug or UUID for the voice profile")
    name: str = Field(..., description="Display name, e.g. 'My Voice (English Cloned)'")
    language: str = Field(..., description="Target language code: 'uk', 'en', 'de', 'pl', etc.")
    engine_type: Literal["builtin", "cloned"] = Field(
        ..., description="Synthesis engine type: 'builtin' (fast ONNX) or 'cloned' (zero-shot)"
    )
    model_name: Optional[str] = Field(
        default=None, description="Identifier of the ONNX base model (e.g. 'uk_UA-lada-medium')"
    )
    reference_audio_path: Optional[str] = Field(
        default=None, description="Absolute or relative path to 5-10s WAV reference sample"
    )
    speaker_id: Optional[int] = Field(
        default=0, description="Optional speaker index for multi-speaker ONNX models"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC creation timestamp",
    )


class VoiceSelection(BaseModel):
    """User selection specifying synthesis mode and voice identifier."""

    mode: Literal["cloud", "local", "cloned"] = Field(
        ..., description="Voice mode: 'cloud' (Gemini), 'local' (Piper ONNX), or 'cloned'"
    )
    voice_id: str = Field(
        ..., description="Identifier of the selected voice (e.g. 'Puck', 'uk_lada', or profile UUID)"
    )


class VoiceCategoryOption(BaseModel):
    """Categorized option for voice selectors in UI."""

    id: str = Field(..., description="Voice identifier")
    name: str = Field(..., description="Display label")
    mode: Literal["cloud", "local", "cloned"] = Field(..., description="Category mode")
    language: str = Field(..., description="Language code")
    description: Optional[str] = Field(default=None, description="Descriptive subtitle or tags")
    sample_url: Optional[str] = Field(default=None, description="URL or endpoint to sample audio preview")


class CreateVoiceProfilePayload(BaseModel):
    name: str
    language: str
    engine_type: Literal["builtin", "cloned"]
    model_name: Optional[str] = None


class TestSynthesizePayload(BaseModel):
    text: str
    voice_id: str
    mode: Literal["cloud", "local", "cloned"]
    language: Optional[str] = None
