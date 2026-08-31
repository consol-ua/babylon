import os
import asyncio
import numpy as np
from typing import Callable, Optional
from google import genai
from google.genai import types


class GeminiLiveAudioPipeline:
    """End-to-End Real-Time Translation and Voiceover using Gemini 3.5 Live Translate."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        target_lang: str = "uk",
        sample_rate: int = 16000,
    ) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.target_lang = target_lang
        self.sample_rate = sample_rate

        self.client: Optional[genai.Client] = None
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)

        self.is_running: bool = False

        # Callbacks for telemetry and UI updates
        self.on_stt_result: Optional[Callable[[str, bool], None]] = None
        self.on_translated_result: Optional[Callable[[str], None]] = None

    def set_api_key(self, api_key: str) -> None:
        """Update Gemini API Key dynamically."""
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)

    async def run(
        self,
        input_queue: asyncio.Queue[bytes],
        tts_playback_queue: asyncio.Queue[np.ndarray],
    ) -> None:
        """Runs bidirectional streaming audio translation session with Gemini Live API."""
        self.is_running = True

        if not self.client:
            print("[GeminiLiveAudioPipeline] Warning: No GEMINI_API_KEY provided. Running in simulation mode.")
            await self._run_simulation(input_queue, tts_playback_queue)
            return

        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            translation_config=types.TranslationConfig(
                target_language_code=self.target_lang,
                echo_target_language=True,
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )

        try:
            print(f"[GeminiLiveAudioPipeline] Connecting to gemini-3.5-live-translate-preview (target: {self.target_lang})...")
            async with self.client.aio.live.connect(
                model="gemini-3.5-live-translate-preview",
                config=config,
            ) as session:
                print("[GeminiLiveAudioPipeline] Live session connected.")

                async def send_audio_worker() -> None:
                    """Continuously stream microphone/system audio chunks to Gemini."""
                    while self.is_running:
                        try:
                            chunk = await input_queue.get()
                            if chunk is None:
                                break
                            await session.send_realtime_input(
                                audio=types.Blob(
                                    data=chunk,
                                    mime_type=f"audio/pcm;rate={self.sample_rate}",
                                )
                            )
                        except Exception as e:
                            print(f"[Gemini Sender Error] {e}")
                            break

                async def receive_audio_worker() -> None:
                    """Receive real-time translated audio chunks and transcriptions from Gemini."""
                    async for response in session.receive():
                        if not self.is_running:
                            break

                        content = response.server_content
                        if not content:
                            continue

                        # Process received translated audio PCM (24kHz little-endian 16-bit mono)
                        if content.model_turn:
                            for part in content.model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    raw_pcm_24k = part.inline_data.data
                                    # Convert raw 24kHz PCM to numpy array
                                    audio_24k = np.frombuffer(raw_pcm_24k, dtype=np.int16)
                                    
                                    # Resample 24kHz down to 16kHz to match engine
                                    if len(audio_24k) > 0:
                                        num_samples_16k = int(len(audio_24k) * (16000 / 24000))
                                        orig_indices = np.linspace(0, len(audio_24k) - 1, len(audio_24k))
                                        new_indices = np.linspace(0, len(audio_24k) - 1, num_samples_16k)
                                        audio_16k = np.interp(new_indices, orig_indices, audio_24k).astype(np.int16)
                                        
                                        await tts_playback_queue.put(audio_16k)

                        # User input transcription (Source text)
                        if content.input_transcription and content.input_transcription.text:
                            if self.on_stt_result:
                                self.on_stt_result(content.input_transcription.text, True)

                        # Output translation transcription (Target text)
                        if content.output_transcription and content.output_transcription.text:
                            if self.on_translated_result:
                                self.on_translated_result(content.output_transcription.text)

                        # Interruption handling
                        if content.interrupted:
                            # Clear any buffered playback audio on user interruption
                            while not tts_playback_queue.empty():
                                try:
                                    tts_playback_queue.get_nowait()
                                except asyncio.QueueEmpty:
                                    break

                send_task = asyncio.create_task(send_audio_worker())
                recv_task = asyncio.create_task(receive_audio_worker())

                done, pending = await asyncio.wait(
                    [send_task, recv_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                for task in done:
                    if task.exception() and not isinstance(task.exception(), asyncio.CancelledError):
                        print(f"[GeminiLiveAudioPipeline Worker Error] {task.exception()}")

        except Exception as e:
            print(f"[GeminiLiveAudioPipeline Session Error] {e}")
        finally:
            self.is_running = False

    async def _run_simulation(
        self,
        input_queue: asyncio.Queue[bytes],
        tts_playback_queue: asyncio.Queue[np.ndarray],
    ) -> None:
        """Simulate translation stream when no API key is provided."""
        while self.is_running:
            await asyncio.sleep(2.0)
            if not input_queue.empty():
                await input_queue.get()
                if self.on_stt_result:
                    self.on_stt_result("Live speech detected in system audio stream.", True)
                if self.on_translated_result:
                    self.on_translated_result(f"Живе мовлення виявлено в аудіопотоці ({self.target_lang}).")

                # Generate brief synthetic confirmation tone
                t = np.linspace(0, 0.4, int(self.sample_rate * 0.4), False)
                tone = (np.sin(2 * np.pi * 520 * t) * 0.3 * 32767).astype(np.int16)
                await tts_playback_queue.put(tone)

    def stop(self) -> None:
        """Stops the live translation session."""
        self.is_running = False
