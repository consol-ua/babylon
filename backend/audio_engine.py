from __future__ import annotations
import asyncio
import os
import wave
import numpy as np
import pyaudio
from typing import List, Dict, Optional, Callable


class DualChannelAudioEngine:
    """
    High-performance audio engine for bidirectional translation and sample playback.
    
    Supports:
    1. Outgoing Channel (My Mic -> Gemini UA->Target -> Virtual Output for Zoom/Meet)
    2. Incoming Channel (Zoom/Meet Sound -> Gemini Target->UA -> Mix & Ducking -> Headphones)
    3. Sample Testing Channel (WAV sample -> Gemini Target->UA -> Mix & Ducking -> Headphones)
    """

    def __init__(
        self,
        format_type: int = pyaudio.paInt16,
        channels: int = 1,
        rate: int = 16000,
        chunk_size: int = 1024,
    ) -> None:
        self.format_type = format_type
        self.channels = channels
        self.rate = rate
        self.chunk_size = chunk_size

        self.p: pyaudio.PyAudio = pyaudio.PyAudio()

        # Outgoing streams
        self.my_mic_stream: Optional[pyaudio.Stream] = None
        self.call_virtual_mic_stream: Optional[pyaudio.Stream] = None

        # Incoming streams
        self.call_input_stream: Optional[pyaudio.Stream] = None
        self.headphones_stream: Optional[pyaudio.Stream] = None

        # Audio Queues
        self.outgoing_input_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.outgoing_tts_queue: asyncio.Queue[np.ndarray] = asyncio.Queue()

        self.incoming_input_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.incoming_tts_queue: asyncio.Queue[np.ndarray] = asyncio.Queue()

        # Ducking configuration
        self.ducking_factor: float = 0.2
        self.is_incoming_ducking: bool = False

        # Status flags
        self.is_call_running: bool = False
        self.is_sample_running: bool = False

        # Telemetry Callbacks
        self.outgoing_telemetry_cb: Optional[Callable[[float], None]] = None
        self.incoming_telemetry_cb: Optional[Callable[[float, bool], None]] = None

    def list_devices(self) -> List[Dict[str, str | int]]:
        """List all available audio input and output devices."""
        devices: List[Dict[str, str | int]] = []
        device_count = self.p.get_device_count()

        for i in range(device_count):
            try:
                info = self.p.get_device_info_by_index(i)
                devices.append(
                    {
                        "index": i,
                        "name": str(info.get("name")),
                        "max_input_channels": int(info.get("maxInputChannels", 0)),
                        "max_output_channels": int(info.get("maxOutputChannels", 0)),
                        "default_sample_rate": int(info.get("defaultSampleRate", 0)),
                    }
                )
            except Exception:
                pass
        return devices

    def set_ducking_factor(self, factor: float) -> None:
        """Set ducking attenuation factor (0.0 = full mute, 1.0 = no ducking)."""
        self.ducking_factor = max(0.0, min(1.0, factor))

    def _calculate_rms_db(self, audio_data: np.ndarray) -> float:
        """Calculate RMS volume in dB."""
        float_data = audio_data.astype(np.float32)
        rms = np.sqrt(np.mean(float_data**2))
        if rms > 0:
            return float(20 * np.log10(rms / 32767.0))
        return -100.0

    def _apply_ducking_and_mix(
        self, background_chunk: np.ndarray, voiceover_chunk: Optional[np.ndarray]
    ) -> np.ndarray:
        """Attenuate incoming original audio and mix in Ukrainian translated voice."""
        bg_float = background_chunk.astype(np.float32)

        if voiceover_chunk is not None and len(voiceover_chunk) > 0:
            self.is_incoming_ducking = True
            ducked_bg = bg_float * self.ducking_factor

            vo_float = voiceover_chunk.astype(np.float32)
            if len(vo_float) < len(ducked_bg):
                vo_float = np.pad(vo_float, (0, len(ducked_bg) - len(vo_float)))
            elif len(vo_float) > len(ducked_bg):
                vo_float = vo_float[: len(ducked_bg)]

            mixed = ducked_bg + vo_float
        else:
            self.is_incoming_ducking = False
            mixed = bg_float

        return np.clip(mixed, -32768, 32767).astype(np.int16)

    def start_call(
        self,
        my_mic_index: Optional[int] = None,
        call_virtual_mic_index: Optional[int] = None,
        call_input_index: Optional[int] = None,
        headphones_index: Optional[int] = None,
    ) -> None:
        """Start all 4 audio streams for full-duplex call translation."""
        if self.is_call_running:
            return

        # 1. Outgoing Input (My Microphone)
        self.my_mic_stream = self.p.open(
            format=self.format_type,
            channels=self.channels,
            rate=self.rate,
            input=True,
            input_device_index=my_mic_index,
            frames_per_buffer=self.chunk_size,
        )

        # 2. Outgoing Output (Virtual Mic for Zoom/Meet)
        if call_virtual_mic_index is not None:
            self.call_virtual_mic_stream = self.p.open(
                format=self.format_type,
                channels=self.channels,
                rate=self.rate,
                output=True,
                output_device_index=call_virtual_mic_index,
                frames_per_buffer=self.chunk_size,
            )

        # 3. Incoming Input (Audio from Zoom/Meet)
        if call_input_index is not None:
            self.call_input_stream = self.p.open(
                format=self.format_type,
                channels=self.channels,
                rate=self.rate,
                input=True,
                input_device_index=call_input_index,
                frames_per_buffer=self.chunk_size,
            )

        # 4. Incoming Output (Headphones / Speakers)
        self.headphones_stream = self.p.open(
            format=self.format_type,
            channels=self.channels,
            rate=self.rate,
            output=True,
            output_device_index=headphones_index,
            frames_per_buffer=self.chunk_size,
        )

        self.is_call_running = True

    def stop_call(self) -> None:
        """Stop and close all call streams."""
        self.is_call_running = False

        for stream_attr in [
            "my_mic_stream",
            "call_virtual_mic_stream",
            "call_input_stream",
            "headphones_stream",
        ]:
            stream = getattr(self, stream_attr)
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
                setattr(self, stream_attr, None)

        self._drain_queues()

    def start_sample_test(self, headphones_index: Optional[int] = None) -> None:
        """Start headphones stream for testing demo sample audio."""
        if self.is_sample_running:
            return

        self.headphones_stream = self.p.open(
            format=self.format_type,
            channels=self.channels,
            rate=self.rate,
            output=True,
            output_device_index=headphones_index,
            frames_per_buffer=self.chunk_size,
        )
        self.is_sample_running = True

    def stop_sample_test(self) -> None:
        """Stop sample testing stream."""
        self.is_sample_running = False
        if self.headphones_stream:
            try:
                self.headphones_stream.stop_stream()
                self.headphones_stream.close()
            except Exception:
                pass
            self.headphones_stream = None

        self._drain_queues()

    def _drain_queues(self) -> None:
        """Clear remaining items from audio queues."""
        for q in [
            self.outgoing_input_queue,
            self.outgoing_tts_queue,
            self.incoming_input_queue,
            self.incoming_tts_queue,
        ]:
            while not q.empty():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    break

    async def outgoing_process_loop(self) -> None:
        """
        Outgoing loop:
        Reads User Mic -> Pushes to Gemini Live (UA->Target) -> Reads clean TTS -> Writes to Virtual Mic.
        """
        loop = asyncio.get_running_loop()

        while self.is_call_running:
            if not self.my_mic_stream:
                await asyncio.sleep(0.01)
                continue

            try:
                # Read user microphone chunk
                raw_mic_bytes = await loop.run_in_executor(
                    None,
                    self.my_mic_stream.read,
                    self.chunk_size,
                    False,
                )

                # Push to AI queue
                await self.outgoing_input_queue.put(raw_mic_bytes)

                mic_audio = np.frombuffer(raw_mic_bytes, dtype=np.int16)
                if self.outgoing_telemetry_cb:
                    db = self._calculate_rms_db(mic_audio)
                    self.outgoing_telemetry_cb(db)

                # If translated foreign speech is ready, output clean speech to Zoom/Meet virtual mic
                if (
                    self.call_virtual_mic_stream
                    and not self.outgoing_tts_queue.empty()
                ):
                    tts_chunk = await self.outgoing_tts_queue.get()
                    clipped_tts = np.clip(tts_chunk, -32768, 32767).astype(np.int16)
                    await loop.run_in_executor(
                        None, self.call_virtual_mic_stream.write, clipped_tts.tobytes()
                    )

            except Exception as e:
                print(f"[Outgoing Loop Error] {e}")
                await asyncio.sleep(0.01)

    async def incoming_process_loop(self) -> None:
        """
        Incoming loop:
        Reads Call Audio (BlackHole) -> Pushes to Gemini Live (Target->UA) -> Mixes with Ukrainian Voice -> Writes to Headphones.
        """
        loop = asyncio.get_running_loop()

        while self.is_call_running:
            if not self.call_input_stream or not self.headphones_stream:
                await asyncio.sleep(0.01)
                continue

            try:
                # Read incoming call audio chunk
                raw_call_bytes = await loop.run_in_executor(
                    None,
                    self.call_input_stream.read,
                    self.chunk_size,
                    False,
                )

                # Push to AI queue
                await self.incoming_input_queue.put(raw_call_bytes)

                call_audio_chunk = np.frombuffer(raw_call_bytes, dtype=np.int16)

                # Pop translated Ukrainian voiceover chunk if available
                voiceover_chunk: Optional[np.ndarray] = None
                if not self.incoming_tts_queue.empty():
                    voiceover_chunk = await self.incoming_tts_queue.get()

                # Mix with ducking
                mixed_output = self._apply_ducking_and_mix(
                    call_audio_chunk, voiceover_chunk
                )

                if self.incoming_telemetry_cb:
                    db = self._calculate_rms_db(call_audio_chunk)
                    self.incoming_telemetry_cb(db, self.is_incoming_ducking)

                # Output to user headphones
                await loop.run_in_executor(
                    None, self.headphones_stream.write, mixed_output.tobytes()
                )

            except Exception as e:
                print(f"[Incoming Loop Error] {e}")
                await asyncio.sleep(0.01)

    async def sample_playback_loop(self, sample_filepath: str) -> None:
        """
        Feeds pre-recorded WAV sample chunk-by-chunk into incoming AI pipeline and plays mixed Ukrainian voice to headphones.
        """
        if not os.path.exists(sample_filepath):
            print(f"[Sample Error] File not found: {sample_filepath}")
            return

        loop = asyncio.get_running_loop()

        try:
            with wave.open(sample_filepath, "rb") as wf:
                framerate = wf.getframerate()
                chunk_duration_sec = self.chunk_size / framerate

                while self.is_sample_running:
                    raw_bytes = wf.readframes(self.chunk_size)
                    if not raw_bytes:
                        # Reached end of audio file
                        break

                    # Ensure chunk length matches
                    chunk_audio = np.frombuffer(raw_bytes, dtype=np.int16)
                    if len(chunk_audio) < self.chunk_size:
                        chunk_audio = np.pad(chunk_audio, (0, self.chunk_size - len(chunk_audio)))
                        raw_bytes = chunk_audio.tobytes()

                    # Push to AI pipeline
                    await self.incoming_input_queue.put(raw_bytes)

                    # Pop translated Ukrainian voiceover if ready
                    voiceover_chunk: Optional[np.ndarray] = None
                    if not self.incoming_tts_queue.empty():
                        voiceover_chunk = await self.incoming_tts_queue.get()

                    mixed_output = self._apply_ducking_and_mix(
                        chunk_audio, voiceover_chunk
                    )

                    if self.incoming_telemetry_cb:
                        db = self._calculate_rms_db(chunk_audio)
                        self.incoming_telemetry_cb(db, self.is_incoming_ducking)

                    if self.headphones_stream:
                        await loop.run_in_executor(
                            None, self.headphones_stream.write, mixed_output.tobytes()
                        )

                    # Maintain real-time pace
                    await asyncio.sleep(chunk_duration_sec * 0.95)

                # Allow lingering voiceover queue to finish playing out
                drain_timeout = 10.0
                start_time = asyncio.get_event_loop().time()
                while self.is_sample_running and not self.incoming_tts_queue.empty():
                    if asyncio.get_event_loop().time() - start_time > drain_timeout:
                        break
                    voiceover_chunk = await self.incoming_tts_queue.get()
                    silent_bg = np.zeros(len(voiceover_chunk), dtype=np.int16)
                    mixed_output = self._apply_ducking_and_mix(silent_bg, voiceover_chunk)
                    if self.headphones_stream:
                        await loop.run_in_executor(
                            None, self.headphones_stream.write, mixed_output.tobytes()
                        )
                    await asyncio.sleep(0.05)

        except Exception as e:
            print(f"[Sample Playback Error] {e}")
        finally:
            self.is_sample_running = False

    def terminate(self) -> None:
        """Cleanup PyAudio instance."""
        self.stop_call()
        self.stop_sample_test()
        self.p.terminate()
