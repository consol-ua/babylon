from __future__ import annotations
import asyncio
import os
import wave
import time
import threading
import numpy as np
import pyaudio
from typing import List, Dict, Optional, Callable


class AudioStreamBuffer:
    """
    Thread-safe FIFO sample buffer with jitter buffering (pre-buffering).
    Preserves 100% of received audio samples without truncating or discarding.
    """

    def __init__(self, sample_rate: int = 16000, jitter_buffer_ms: int = 150) -> None:
        self.sample_rate = sample_rate
        self.jitter_buffer_ms = jitter_buffer_ms
        self._buffer = np.array([], dtype=np.int16)
        self._is_buffering = True
        self._last_push_time = 0.0

    def set_jitter_buffer_ms(self, ms: int) -> None:
        """Update jitter buffer cushion size in milliseconds."""
        self.jitter_buffer_ms = max(50, min(400, ms))

    @property
    def target_buffer_samples(self) -> int:
        return int(self.sample_rate * (self.jitter_buffer_ms / 1000.0))

    def push(self, samples: np.ndarray) -> None:
        """Append incoming samples of any length to the FIFO buffer."""
        if len(samples) == 0:
            return
        if len(self._buffer) == 0 and self._is_buffering:
            # First arrival of new utterance
            self._is_buffering = True

        self._buffer = np.concatenate((self._buffer, samples))
        self._last_push_time = time.time()

        if self._is_buffering and len(self._buffer) >= self.target_buffer_samples:
            self._is_buffering = False

    def pop(self, num_samples: int) -> Optional[np.ndarray]:
        """
        Extract exactly num_samples for output playback.
        Returns None if buffering or empty.
        """
        if len(self._buffer) == 0:
            self._is_buffering = True
            return None

        if self._is_buffering:
            # If buffer has accumulated enough samples or timed out waiting
            if len(self._buffer) >= self.target_buffer_samples or (time.time() - self._last_push_time > 0.25):
                self._is_buffering = False
            else:
                return None

        if len(self._buffer) >= num_samples:
            chunk = self._buffer[:num_samples]
            self._buffer = self._buffer[num_samples:]
            return chunk
        else:
            # Drain remaining samples and pad with silence to avoid click
            chunk = np.pad(self._buffer, (0, num_samples - len(self._buffer)))
            self._buffer = np.array([], dtype=np.int16)
            self._is_buffering = True
            return chunk

    def clear(self) -> None:
        """Clear buffer on interruption or stop."""
        self._buffer = np.array([], dtype=np.int16)
        self._is_buffering = True

    def has_audio(self) -> bool:
        return len(self._buffer) > 0


class SmartDuckingDSP:
    """
    Sidechain compression with smooth attack, hold time, and release curves.
    Prevents volume pumping and audio popping between words.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        ducking_factor: float = 0.2,
        attack_ms: float = 40.0,
        hold_ms: float = 500.0,
        release_ms: float = 200.0,
    ) -> None:
        self.sample_rate = sample_rate
        self.ducking_factor = max(0.0, min(1.0, ducking_factor))
        self.attack_ms = attack_ms
        self.hold_ms = hold_ms
        self.release_ms = release_ms

        self.current_gain: float = 1.0
        self.last_voice_activity_time: float = 0.0
        self.is_active: bool = False

    def set_ducking_factor(self, factor: float) -> None:
        self.ducking_factor = max(0.0, min(1.0, factor))

    def process(
        self,
        background_chunk: np.ndarray,
        voiceover_chunk: Optional[np.ndarray],
    ) -> tuple[np.ndarray, bool]:
        """
        Smoothly attenuates background audio and mixes in the voiceover.
        Returns: (mixed_pcm_int16, is_ducking_active)
        """
        chunk_len = len(background_chunk)
        if chunk_len == 0:
            return background_chunk, False

        now = time.time()
        chunk_duration = chunk_len / self.sample_rate

        has_voiceover = voiceover_chunk is not None and np.any(np.abs(voiceover_chunk) > 50)

        if has_voiceover:
            self.last_voice_activity_time = now
            target_gain = self.ducking_factor
            self.is_active = True
        else:
            time_since_voice = (now - self.last_voice_activity_time) * 1000.0
            if time_since_voice < self.hold_ms:
                # Still within hold window
                target_gain = self.ducking_factor
                self.is_active = True
            else:
                target_gain = 1.0
                self.is_active = False

        # Calculate gain transition rates
        if target_gain < self.current_gain:
            # Attack phase (fade down)
            rate_per_sec = (1.0 - self.ducking_factor) / (self.attack_ms / 1000.0)
            max_gain_delta = rate_per_sec * chunk_duration
            end_gain = max(target_gain, self.current_gain - max_gain_delta)
        else:
            # Release phase (fade back up)
            rate_per_sec = (1.0 - self.ducking_factor) / (self.release_ms / 1000.0)
            max_gain_delta = rate_per_sec * chunk_duration
            end_gain = min(target_gain, self.current_gain + max_gain_delta)

        # Create smooth linear gain ramp for this chunk
        gain_ramp = np.linspace(self.current_gain, end_gain, chunk_len, dtype=np.float32)
        self.current_gain = end_gain

        # Apply gain ramp to background
        bg_float = background_chunk.astype(np.float32)
        ducked_bg = bg_float * gain_ramp

        # Mix voiceover if present
        if voiceover_chunk is not None and len(voiceover_chunk) > 0:
            vo_float = voiceover_chunk.astype(np.float32)
            if len(vo_float) < chunk_len:
                vo_float = np.pad(vo_float, (0, chunk_len - len(vo_float)))
            elif len(vo_float) > chunk_len:
                vo_float = vo_float[:chunk_len]
            mixed = ducked_bg + vo_float
        else:
            mixed = ducked_bg

        mixed_clipped = np.clip(mixed, -32768, 32767).astype(np.int16)
        is_ducking = self.current_gain < 0.95 or self.is_active
        return mixed_clipped, is_ducking


class DualChannelAudioEngine:
    """
    High-performance audio engine for bidirectional translation and sample playback.
    Integrated with smart DSP ducking and jitter FIFO streaming.
    Thread-safe PortAudio stream management to eliminate race conditions and double-free issues.
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

        self._lock = threading.RLock()
        self.p: pyaudio.PyAudio = pyaudio.PyAudio()

        # Outgoing streams
        self.my_mic_stream: Optional[pyaudio.Stream] = None
        self.call_virtual_mic_stream: Optional[pyaudio.Stream] = None

        # Incoming streams
        self.call_input_stream: Optional[pyaudio.Stream] = None
        self.headphones_stream: Optional[pyaudio.Stream] = None

        # Input Queues for Gemini STT
        self.outgoing_input_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.incoming_input_queue: asyncio.Queue[bytes] = asyncio.Queue()

        # Audio Stream FIFO Buffers for Playback (Smooth playback, no discarded samples)
        self.outgoing_playback_buffer = AudioStreamBuffer(sample_rate=rate, jitter_buffer_ms=150)
        self.incoming_playback_buffer = AudioStreamBuffer(sample_rate=rate, jitter_buffer_ms=150)

        # Smart Ducking DSP Engines
        self.incoming_ducking_dsp = SmartDuckingDSP(sample_rate=rate, ducking_factor=0.2)

        # Status flags
        self.is_call_running: bool = False
        self.is_sample_running: bool = False
        self.is_incoming_ducking: bool = False

        # Telemetry Callbacks
        self.outgoing_telemetry_cb: Optional[Callable[[float], None]] = None
        self.incoming_telemetry_cb: Optional[Callable[[float, bool], None]] = None

    def _safe_read_stream(self, stream: Optional[pyaudio.Stream], num_frames: int) -> Optional[bytes]:
        """Thread-safe stream read with overflow handling."""
        with self._lock:
            if not stream:
                return None
            try:
                if not stream.is_active() or stream.is_stopped():
                    return None
                return stream.read(num_frames, exception_on_overflow=False)
            except Exception:
                return None

    def _safe_write_stream(self, stream: Optional[pyaudio.Stream], data: bytes) -> None:
        """Thread-safe stream write."""
        with self._lock:
            if not stream:
                return
            try:
                if not stream.is_active() or stream.is_stopped():
                    return
                stream.write(data)
            except Exception:
                pass

    def _safe_close_stream(self, stream: Optional[pyaudio.Stream]) -> None:
        """Thread-safe and idempotent stream stop and close."""
        with self._lock:
            if not stream:
                return
            try:
                if stream.is_active():
                    stream.stop_stream()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

    def list_devices(self) -> List[Dict[str, str | int]]:
        """List all available audio input and output devices."""
        devices: List[Dict[str, str | int]] = []
        with self._lock:
            try:
                device_count = self.p.get_device_count()
            except Exception:
                return devices

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
        self.incoming_ducking_dsp.set_ducking_factor(factor)

    def set_jitter_buffer_ms(self, ms: int) -> None:
        """Set jitter buffer size in ms for both playback channels."""
        self.outgoing_playback_buffer.set_jitter_buffer_ms(ms)
        self.incoming_playback_buffer.set_jitter_buffer_ms(ms)

    def _calculate_rms_db(self, audio_data: np.ndarray) -> float:
        """Calculate RMS volume in dB."""
        float_data = audio_data.astype(np.float32)
        rms = np.sqrt(np.mean(float_data**2))
        if rms > 0:
            return float(20 * np.log10(rms / 32767.0))
        return -100.0

    def push_outgoing_tts_chunk(self, chunk: np.ndarray) -> None:
        """Push translated speech chunk to outgoing buffer for Zoom/Meet."""
        self.outgoing_playback_buffer.push(chunk)

    def push_incoming_tts_chunk(self, chunk: np.ndarray) -> None:
        """Push translated speech chunk to incoming buffer for headphones."""
        self.incoming_playback_buffer.push(chunk)

    def clear_playback_buffers(self) -> None:
        """Clear buffers on interrupt or stop."""
        self.outgoing_playback_buffer.clear()
        self.incoming_playback_buffer.clear()

    def start_call(
        self,
        my_mic_index: Optional[int] = None,
        call_virtual_mic_index: Optional[int] = None,
        call_input_index: Optional[int] = None,
        headphones_index: Optional[int] = None,
    ) -> None:
        """Start all audio streams for full-duplex call translation."""
        with self._lock:
            if self.is_call_running:
                return

            self.clear_playback_buffers()

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

    async def stop_call(self) -> None:
        """Gracefully stop and close all call streams."""
        if not self.is_call_running:
            return

        self.is_call_running = False
        await asyncio.sleep(0.05)

        with self._lock:
            for stream_attr in [
                "my_mic_stream",
                "call_virtual_mic_stream",
                "call_input_stream",
                "headphones_stream",
            ]:
                stream = getattr(self, stream_attr)
                if stream:
                    self._safe_close_stream(stream)
                    setattr(self, stream_attr, None)

        self._drain_queues()
        self.clear_playback_buffers()

    def start_sample_test(self, headphones_index: Optional[int] = None) -> None:
        """Start headphones stream for testing demo sample audio."""
        with self._lock:
            if self.is_sample_running:
                return

            self.clear_playback_buffers()

            self.headphones_stream = self.p.open(
                format=self.format_type,
                channels=self.channels,
                rate=self.rate,
                output=True,
                output_device_index=headphones_index,
                frames_per_buffer=self.chunk_size,
            )
            self.is_sample_running = True

    async def stop_sample_test(self) -> None:
        """Gracefully stop sample testing stream."""
        if not self.is_sample_running:
            return

        self.is_sample_running = False
        await asyncio.sleep(0.05)

        with self._lock:
            if self.headphones_stream:
                self._safe_close_stream(self.headphones_stream)
                self.headphones_stream = None

        self._drain_queues()
        self.clear_playback_buffers()

    def _drain_queues(self) -> None:
        """Clear remaining items from audio queues."""
        for q in [self.outgoing_input_queue, self.incoming_input_queue]:
            while not q.empty():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    break

    async def outgoing_process_loop(self) -> None:
        """
        Outgoing loop:
        Reads User Mic -> Pushes to Gemini Live (UA->Target) -> Reads clean TTS from buffer -> Writes to Virtual Mic.
        """
        loop = asyncio.get_running_loop()

        while self.is_call_running:
            if not self.my_mic_stream:
                await asyncio.sleep(0.01)
                continue

            try:
                raw_mic_bytes = await loop.run_in_executor(
                    None,
                    self._safe_read_stream,
                    self.my_mic_stream,
                    self.chunk_size,
                )

                if not raw_mic_bytes or not self.is_call_running:
                    await asyncio.sleep(0.01)
                    continue

                await self.outgoing_input_queue.put(raw_mic_bytes)

                mic_audio = np.frombuffer(raw_mic_bytes, dtype=np.int16)
                if self.outgoing_telemetry_cb:
                    db = self._calculate_rms_db(mic_audio)
                    self.outgoing_telemetry_cb(db)

                # Output clean translated speech to Zoom/Meet virtual mic
                if self.call_virtual_mic_stream and self.is_call_running:
                    tts_chunk = self.outgoing_playback_buffer.pop(self.chunk_size)
                    if tts_chunk is not None:
                        await loop.run_in_executor(
                            None,
                            self._safe_write_stream,
                            self.call_virtual_mic_stream,
                            tts_chunk.tobytes(),
                        )

            except Exception as e:
                print(f"[Outgoing Loop Error] {e}")
                await asyncio.sleep(0.01)

    async def incoming_process_loop(self) -> None:
        """
        Incoming loop:
        Reads Call Audio (BlackHole) -> Pushes to Gemini Live -> Mixes with Ukrainian Voice via SmartDuckingDSP -> Writes to Headphones.
        """
        loop = asyncio.get_running_loop()

        while self.is_call_running:
            if not self.call_input_stream or not self.headphones_stream:
                await asyncio.sleep(0.01)
                continue

            try:
                raw_call_bytes = await loop.run_in_executor(
                    None,
                    self._safe_read_stream,
                    self.call_input_stream,
                    self.chunk_size,
                )

                if not raw_call_bytes or not self.is_call_running:
                    await asyncio.sleep(0.01)
                    continue

                await self.incoming_input_queue.put(raw_call_bytes)
                call_audio_chunk = np.frombuffer(raw_call_bytes, dtype=np.int16)

                # Extract exact-length voiceover chunk from smooth FIFO buffer
                voiceover_chunk = self.incoming_playback_buffer.pop(self.chunk_size)

                # Mix with smart attack/hold/release ducking
                mixed_output, is_ducking = self.incoming_ducking_dsp.process(
                    call_audio_chunk, voiceover_chunk
                )
                self.is_incoming_ducking = is_ducking

                if self.incoming_telemetry_cb:
                    db = self._calculate_rms_db(call_audio_chunk)
                    self.incoming_telemetry_cb(db, self.is_incoming_ducking)

                if self.headphones_stream and self.is_call_running:
                    await loop.run_in_executor(
                        None,
                        self._safe_write_stream,
                        self.headphones_stream,
                        mixed_output.tobytes(),
                    )

            except Exception as e:
                print(f"[Incoming Loop Error] {e}")
                await asyncio.sleep(0.01)

    async def sample_playback_loop(self, sample_filepath: str) -> None:
        """
        Feeds pre-recorded WAV sample into incoming AI pipeline and plays mixed Ukrainian voice to headphones.
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
                        break

                    chunk_audio = np.frombuffer(raw_bytes, dtype=np.int16)
                    if len(chunk_audio) < self.chunk_size:
                        chunk_audio = np.pad(chunk_audio, (0, self.chunk_size - len(chunk_audio)))
                        raw_bytes = chunk_audio.tobytes()

                    await self.incoming_input_queue.put(raw_bytes)

                    # Extract exact voiceover chunk from buffer
                    voiceover_chunk = self.incoming_playback_buffer.pop(self.chunk_size)

                    mixed_output, is_ducking = self.incoming_ducking_dsp.process(
                        chunk_audio, voiceover_chunk
                    )
                    self.is_incoming_ducking = is_ducking

                    if self.incoming_telemetry_cb:
                        db = self._calculate_rms_db(chunk_audio)
                        self.incoming_telemetry_cb(db, self.is_incoming_ducking)

                    if self.headphones_stream and self.is_sample_running:
                        await loop.run_in_executor(
                            None,
                            self._safe_write_stream,
                            self.headphones_stream,
                            mixed_output.tobytes(),
                        )

                    await asyncio.sleep(chunk_duration_sec * 0.95)

                # Allow buffered voiceover queue to finish playing out
                drain_timeout = 8.0
                start_time = time.time()
                while self.is_sample_running and self.incoming_playback_buffer.has_audio():
                    if time.time() - start_time > drain_timeout:
                        break
                    voiceover_chunk = self.incoming_playback_buffer.pop(self.chunk_size)
                    silent_bg = np.zeros(self.chunk_size, dtype=np.int16)
                    mixed_output, is_ducking = self.incoming_ducking_dsp.process(
                        silent_bg, voiceover_chunk
                    )
                    self.is_incoming_ducking = is_ducking
                    if self.incoming_telemetry_cb:
                        self.incoming_telemetry_cb(-100.0, self.is_incoming_ducking)
                    if self.headphones_stream and self.is_sample_running:
                        await loop.run_in_executor(
                            None,
                            self._safe_write_stream,
                            self.headphones_stream,
                            mixed_output.tobytes(),
                        )
                    await asyncio.sleep(chunk_duration_sec * 0.95)

        except Exception as e:
            print(f"[Sample Playback Error] {e}")
        finally:
            self.is_sample_running = False

    async def terminate(self) -> None:
        """Cleanup PyAudio instance safely."""
        await self.stop_call()
        await self.stop_sample_test()
        with self._lock:
            try:
                self.p.terminate()
            except Exception:
                pass
