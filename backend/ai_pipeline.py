import asyncio
import numpy as np
import torch
from typing import AsyncGenerator, Callable, Optional, Dict, Any

# Google Cloud SDK Imports
try:
    from google.cloud import speech_v1 as speech
    from google.cloud import translate_v2 as translate
except ImportError:
    speech = None
    translate = None

# Coqui TTS Imports
try:
    from TTS.api import TTS
except ImportError:
    TTS = None


class AIPipeline:
    """Orchestrates Streaming STT, Machine Translation, and XTTS synthesis with MPS support."""

    def __init__(
        self,
        source_lang: str = "en-US",
        target_lang: str = "uk",
        sample_rate: int = 16000,
        speaker_wav_path: Optional[str] = None,
    ) -> None:
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.sample_rate = sample_rate
        self.speaker_wav_path = speaker_wav_path

        # Determine Apple Silicon MPS or fallback device
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        print(f"[AIPipeline] Initialized with PyTorch device: {self.device}")

        # State and callbacks
        self.is_running = False
        self.on_stt_result: Optional[Callable[[str, bool], None]] = None
        self.on_translated_result: Optional[Callable[[str], None]] = None

        # Google Cloud Clients
        self.speech_client = speech.SpeechClient() if speech else None
        self.translate_client = translate.Client() if translate else None

        # TTS Model initialization
        self.tts_model: Optional[Any] = None

    def initialize_tts(self) -> None:
        """Loads Coqui XTTS model onto the MPS device."""
        if TTS is not None and self.tts_model is None:
            try:
                print("[AIPipeline] Loading XTTSv2 model onto device...")
                self.tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(
                    self.device
                )
                print("[AIPipeline] XTTSv2 loaded successfully.")
            except Exception as e:
                print(f"[AIPipeline Error loading XTTS] {e}")

    async def translate_text(self, text: str) -> str:
        """Translate source text to target language."""
        if not text.strip():
            return ""

        if self.translate_client:
            loop = asyncio.get_running_loop()
            result: Dict[str, Any] = await loop.run_in_executor(
                None,
                lambda: self.translate_client.translate(
                    text, target_language=self.target_lang
                ),
            )
            return str(result.get("translatedText", ""))
        
        # Fallback/Mock for local testing without credentials
        return f"[Translated ({self.target_lang})]: {text}"

    async def synthesize_speech(self, text: str) -> np.ndarray:
        """Synthesizes text using XTTS and yields raw audio buffer (np.int16)."""
        if not text.strip():
            return np.array([], dtype=np.int16)

        loop = asyncio.get_running_loop()

        def _generate() -> np.ndarray:
            if self.tts_model and self.speaker_wav_path:
                # Generate cloned speech using reference audio
                wav_floats = self.tts_model.tts(
                    text=text,
                    speaker_wav=self.speaker_wav_path,
                    language=self.target_lang,
                )
                # Convert float32 [-1.0, 1.0] to int16 [-32768, 32767]
                wav_int16 = (np.array(wav_floats) * 32767).astype(np.int16)
                return wav_int16
            else:
                # Mock synthetic tone for testing pipeline flow
                duration = max(0.5, len(text) * 0.05)
                t = np.linspace(0, duration, int(self.sample_rate * duration), False)
                tone = np.sin(2 * np.pi * 440 * t) * 0.5
                return (tone * 32767).astype(np.int16)

        return await loop.run_in_executor(None, _generate)

    async def _audio_generator(
        self, input_queue: asyncio.Queue[bytes]
    ) -> AsyncGenerator[speech.StreamingRecognizeRequest, None]:
        """Yields audio chunks from the input queue into the Google STT stream."""
        while self.is_running:
            chunk = await input_queue.get()
            if chunk is None:
                return
            yield speech.StreamingRecognizeRequest(audio_content=chunk)

    async def run(
        self,
        input_queue: asyncio.Queue[bytes],
        tts_playback_queue: asyncio.Queue[np.ndarray],
    ) -> None:
        """Main pipeline loop: Streaming STT -> Translate -> XTTS -> Playback Queue."""
        self.is_running = True
        self.initialize_tts()

        while self.is_running:
            try:
                # If Google STT client is available
                if self.speech_client:
                    config = speech.RecognitionConfig(
                        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                        sample_rate_hertz=self.sample_rate,
                        language_code=self.source_lang,
                        enable_automatic_punctuation=True,
                    )
                    streaming_config = speech.StreamingRecognitionConfig(
                        config=config, interim_results=True
                    )

                    requests_gen = self._audio_generator(input_queue)
                    responses = self.speech_client.streaming_recognize(
                        config=streaming_config, requests=requests_gen
                    )

                    for response in responses:
                        if not self.is_running:
                            break

                        for result in response.results:
                            transcript = result.alternatives[0].transcript
                            is_final = result.is_final

                            if self.on_stt_result:
                                self.on_stt_result(transcript, is_final)

                            if is_final:
                                # 1. Translate
                                translated_text = await self.translate_text(transcript)
                                if self.on_translated_result:
                                    self.on_translated_result(translated_text)

                                # 2. Synthesize via XTTS
                                audio_waveform = await self.synthesize_speech(translated_text)

                                # 3. Enqueue to Audio Engine for playback & ducking
                                chunk_size = 1024
                                for i in range(0, len(audio_waveform), chunk_size):
                                    chunk = audio_waveform[i : i + chunk_size]
                                    await tts_playback_queue.put(chunk)
                else:
                    # Simulated STT loop for development/testing without cloud keys
                    await asyncio.sleep(2.0)
                    if not input_queue.empty():
                        await input_queue.get()
                        demo_transcript = "This is a real-time translation demonstration."
                        if self.on_stt_result:
                            self.on_stt_result(demo_transcript, True)
                        
                        translated_text = await self.translate_text(demo_transcript)
                        if self.on_translated_result:
                            self.on_translated_result(translated_text)

                        synth_audio = await self.synthesize_speech(translated_text)
                        for i in range(0, len(synth_audio), 1024):
                            await tts_playback_queue.put(synth_audio[i : i + 1024])

            except Exception as e:
                print(f"[AIPipeline Loop Error] {e}")
                await asyncio.sleep(1.0)

    def stop(self) -> None:
        """Stop the AI processing pipeline."""
        self.is_running = False
