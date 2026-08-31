import os
import asyncio
import numpy as np
from typing import Callable, Optional
from google import genai
from google.genai import types
from google.genai.errors import APIError


class GeminiLiveAudioSession:
    """Independent Gemini 3.5 Live Streaming Session for a single directional audio channel."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        target_lang: str = "uk",
        sample_rate: int = 16000,
        channel_name: str = "channel",
    ) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.target_lang = target_lang
        self.sample_rate = sample_rate
        self.channel_name = channel_name

        self.client: Optional[genai.Client] = None
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[GeminiLiveAudioSession:{self.channel_name}] Init client error: {e}")

        self.is_running: bool = False

        # Callbacks for audio, text, and telemetry
        self.on_audio_chunk: Optional[Callable[[np.ndarray], None]] = None
        self.on_stt_result: Optional[Callable[[str, bool], None]] = None
        self.on_translated_result: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str, str], None]] = None
        self.on_interrupt: Optional[Callable[[], None]] = None

    def set_api_key(self, api_key: str) -> None:
        """Update Gemini API Key dynamically."""
        self.api_key = api_key.strip()
        if self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                self._report_error(f"Помилка ініціалізації клієнта з ключем: {e}", "KEY_ERROR")
        else:
            self.client = None

    def _report_error(self, message: str, error_type: str = "API_ERROR") -> None:
        """Log error and notify UI callback."""
        print(f"[GeminiLive:{self.channel_name} ERROR] ({error_type}) {message}")
        if self.on_error:
            self.on_error(message, error_type)

    async def run(
        self,
        input_queue: asyncio.Queue[bytes],
    ) -> None:
        """Runs bidirectional streaming audio translation session with Gemini Live API."""
        self.is_running = True

        if not self.client or not self.api_key:
            self._report_error(
                "Gemini API ключ не вказано. Запуск у демонстраційному режимі емуляції.",
                "NO_API_KEY"
            )
            await self._run_simulation(input_queue)
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
            print(f"[GeminiLiveAudioSession:{self.channel_name}] Connecting to gemini-3.5-live-translate-preview (target: {self.target_lang})...")
            async with self.client.aio.live.connect(
                model="gemini-3.5-live-translate-preview",
                config=config,
            ) as session:
                print(f"[GeminiLiveAudioSession:{self.channel_name}] Live session connected successfully.")

                async def send_audio_worker() -> None:
                    """Continuously stream audio chunks to Gemini."""
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
                        except asyncio.CancelledError:
                            break
                        except Exception as e:
                            self._report_error(f"Помилка відправки аудіо: {e}", "SEND_ERROR")
                            break

                async def receive_audio_worker() -> None:
                    """Receive real-time translated audio chunks and transcriptions from Gemini."""
                    try:
                        async for response in session.receive():
                            if not self.is_running:
                                break

                            content = response.server_content
                            if not content:
                                continue

                            # Process received translated audio PCM (24kHz -> 16kHz resample)
                            if content.model_turn:
                                for part in content.model_turn.parts:
                                    if part.inline_data and part.inline_data.data:
                                        raw_pcm_24k = part.inline_data.data
                                        audio_24k = np.frombuffer(raw_pcm_24k, dtype=np.int16)
                                        
                                        # Resample 24kHz down to 16kHz
                                        if len(audio_24k) > 0:
                                            num_samples_16k = int(len(audio_24k) * (16000 / 24000))
                                            orig_indices = np.linspace(0, len(audio_24k) - 1, len(audio_24k))
                                            new_indices = np.linspace(0, len(audio_24k) - 1, num_samples_16k)
                                            audio_16k = np.interp(new_indices, orig_indices, audio_24k).astype(np.int16)
                                            
                                            # Push complete resampled audio to callback (FIFO buffer)
                                            if self.on_audio_chunk:
                                                self.on_audio_chunk(audio_16k)

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
                                if self.on_interrupt:
                                    self.on_interrupt()

                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        self._report_error(f"Помилка прийому аудіопотоку: {e}", "RECV_ERROR")

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
                        self._report_error(f"Збій у потоці сесії: {task.exception()}", "WORKER_EXCEPTION")

        except APIError as e:
            msg = f"Помилка Gemini API [{e.code}]: {e.message}"
            self._report_error(msg, "API_ERROR")
        except Exception as e:
            err_str = str(e)
            if "403" in err_str or "API_KEY_INVALID" in err_str or "API key not valid" in err_str:
                self._report_error("Недійсний Gemini API ключ (403/401). Перевірте ключ у налаштуваннях.", "INVALID_KEY")
            elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                self._report_error("Перевищено ліміт запитів Gemini API (429 Rate Limit Exceeded).", "RATE_LIMIT")
            else:
                self._report_error(f"Не вдалося встановити сесію Live Translate: {err_str}", "CONNECT_FAILED")
        finally:
            self.is_running = False

    async def _run_simulation(
        self,
        input_queue: asyncio.Queue[bytes],
    ) -> None:
        """Simulate translation stream when no API key is provided."""
        sim_counter = 0
        while self.is_running:
            await asyncio.sleep(2.5)
            if not input_queue.empty():
                await input_queue.get()
                sim_counter += 1
                if self.channel_name == "outgoing":
                    if self.on_stt_result:
                        self.on_stt_result(f"Я розмовляю українською в мікрофон [репліка {sim_counter}]", True)
                    if self.on_translated_result:
                        self.on_translated_result(f"I am speaking English to the call [phrase {sim_counter}] ({self.target_lang})")
                else:
                    if self.on_stt_result:
                        self.on_stt_result(f"Speaking in the meeting stream [phrase {sim_counter}]", True)
                    if self.on_translated_result:
                        self.on_translated_result(f"Співрозмовник говорить у мітингу [фраза {sim_counter}] (переклад українською)")

                # Generate synthetic test tone (440Hz/520Hz)
                freq = 440 if self.channel_name == "outgoing" else 520
                t = np.linspace(0, 0.4, int(self.sample_rate * 0.4), False)
                tone = (np.sin(2 * np.pi * freq * t) * 0.25 * 32767).astype(np.int16)
                if self.on_audio_chunk:
                    self.on_audio_chunk(tone)

    def stop(self) -> None:
        """Stops the live translation session."""
        self.is_running = False
