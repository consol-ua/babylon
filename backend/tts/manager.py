from __future__ import annotations

import logging
from typing import AsyncGenerator, List, Optional
import numpy as np

from .base import BaseTTSProvider
from .cloned_provider import ClonedVoiceProvider
from .models import VoiceCategoryOption, VoiceProfile, VoiceSelection
from .piper_provider import PiperTTSProvider
from .profile_storage import VoiceProfileStorage

logger = logging.getLogger("local_tts_manager")


class LocalTTSManager:
    """
    Orchestrates local speech synthesis providers and voice profile storage.
    Resolves voice selection requests to appropriate engine and executes synthesis.
    """

    CLOUD_VOICES = [
        {"id": "Puck", "name": "Puck (Cloud)", "desc": "Швидкий чіткий чоловічий голос (Google Cloud)"},
        {"id": "Charon", "name": "Charon (Cloud)", "desc": "Природний глибокий чоловічий голос (Google Cloud)"},
        {"id": "Aoede", "name": "Aoede (Cloud)", "desc": "Природний виразний жіночий голос (Google Cloud)"},
        {"id": "Kore", "name": "Kore (Cloud)", "desc": "М'який спокійний жіночий голос (Google Cloud)"},
        {"id": "Fenrir", "name": "Fenrir (Cloud)", "desc": "Авторитетний низький чоловічий голос (Google Cloud)"},
    ]

    def __init__(
        self,
        storage: Optional[VoiceProfileStorage] = None,
        piper_provider: Optional[PiperTTSProvider] = None,
        cloned_provider: Optional[ClonedVoiceProvider] = None,
    ) -> None:
        self.storage = storage or VoiceProfileStorage()
        self.piper_provider = piper_provider or PiperTTSProvider()
        self.cloned_provider = cloned_provider or ClonedVoiceProvider(base_provider=self.piper_provider)

    def get_available_voices(self, language: Optional[str] = None) -> List[VoiceCategoryOption]:
        """
        Return categorized list of Cloud, Built-in Local, and Cloned voice options.
        """
        options: List[VoiceCategoryOption] = []
        lang_filter = language.lower() if language else None

        # 1. Cloud Voices (Gemini Multimodal Live)
        target_cloud_lang = lang_filter or "uk"
        for cv in self.CLOUD_VOICES:
            options.append(
                VoiceCategoryOption(
                    id=cv["id"],
                    name=cv["name"],
                    mode="cloud",
                    language=target_cloud_lang,
                    description=cv["desc"],
                )
            )

        # 2. Built-in Local Profiles
        all_profiles = self.storage.list_profiles(language=lang_filter)
        for p in all_profiles:
            if p.engine_type == "builtin":
                desc = f"Локальний ONNX ({p.model_name or p.name})"
                options.append(
                    VoiceCategoryOption(
                        id=p.id,
                        name=p.name,
                        mode="local",
                        language=p.language,
                        description=desc,
                    )
                )

        # 3. Cloned Profiles
        for p in all_profiles:
            if p.engine_type == "cloned":
                desc = "Клонований голос за зразком мовлення"
                options.append(
                    VoiceCategoryOption(
                        id=p.id,
                        name=p.name,
                        mode="cloned",
                        language=p.language,
                        description=desc,
                    )
                )

        return options

    def _resolve_profile(self, voice_selection: VoiceSelection) -> VoiceProfile:
        """Resolve VoiceSelection to a concrete VoiceProfile with fallback."""
        profile = self.storage.get_profile(voice_selection.voice_id)
        if profile is not None:
            return profile

        # Fallback to default local profile
        defaults = self.storage.list_profiles()
        if defaults:
            fallback = defaults[0]
            logger.warning(
                "Voice ID '%s' not found. Falling back to default profile '%s'.",
                voice_selection.voice_id,
                fallback.id,
            )
            return fallback

        # Absolute emergency fallback
        return VoiceProfile(
            id="emergency_uk",
            name="Emergency Fallback",
            language="uk",
            engine_type="builtin",
            model_name="uk_UA-lada-medium",
        )

    async def synthesize_phrase(
        self, text: str, voice_selection: VoiceSelection
    ) -> np.ndarray:
        """
        Synthesize text using the resolved provider and profile into 16kHz int16 PCM.
        """
        profile = self._resolve_profile(voice_selection)

        if voice_selection.mode == "cloned":
            return await self.cloned_provider.synthesize(text, profile)
        else:
            # Both "local" and preview "cloud" use Piper local provider
            return await self.piper_provider.synthesize(text, profile)

    async def synthesize_stream(
        self, text: str, voice_selection: VoiceSelection
    ) -> AsyncGenerator[np.ndarray, None]:
        """
        Stream synthesized 16kHz int16 PCM audio in real-time chunks.
        """
        profile = self._resolve_profile(voice_selection)

        if voice_selection.mode == "cloned":
            async for chunk in self.cloned_provider.synthesize_stream(text, profile):
                yield chunk
        else:
            async for chunk in self.piper_provider.synthesize_stream(text, profile):
                yield chunk
