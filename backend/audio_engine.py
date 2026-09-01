from __future__ import annotations
import asyncio
import os
import wave
import time
from pathlib import Path
import numpy as np
import pyaudio
from typing import List, Dict, Optional, Callable
import threading

import threading
from collections import deque


class AudioStreamBuffer:
    """
    Thread-safe FIFO sample buffer with jitter buffering (pre-buffering).
    Preserves 100% of received audio samples without truncating or discarding.
    """

    def __init__(self, sample_rate: int = 16000, jitter_buffer_ms: int = 75) -> None:
        self.sample_rate = sample_rate
        self.jitter_buffer_ms = jitter_buffer_ms
        self._chunks: deque[np.ndarray] = deque()
        self._total_samples: int = 0
        self._is_buffering: bool = True
        self._last_push_time: float = 0.0
        self._lock = threading.Lock()

    def set_jitter_buffer_ms(self, ms: int) -> None:
        """Update jitter buffer cushion size in milliseconds."""
        self.jitter_buffer_ms = max(30, min(300, ms))

    @property
    def target_buffer_samples(self) -> int:
        return int(self.sample_rate * (self.jitter_buffer_ms / 1000.0))

    def push(self, samples: np.ndarray) -> None:
        """Append incoming samples to the FIFO buffer."""
        if len(samples) == 0:
            return
        with self._lock:
            self._chunks.append(samples.copy())
            self._total_samples += len(samples)
            self._last_push_time = time.time()
            # Fast-start: start playback as soon as minimum cushion (min of target and 40ms) is reached
            min_cushion = min(self.target_buffer_samples, int(self.sample_rate * 0.04))
            if self._is_buffering and self._total_samples >= min_cushion:
                self._is_buffering = False

    def pop(self, num_samples: int) -> Optional[np.ndarray]:
        """
        Extract exactly num_samples for output playback.
        Returns None if buffering or empty.
        """
        with self._lock:
            if self._total_samples == 0:
                self._is_buffering = True
                return None
            if self._is_buffering:
                min_cushion = min(self.target_buffer_samples, int(self.sample_rate * 0.04))
                if self._total_samples >= min_cushion or (time.time() - self._last_push_time > 0.15):
                    self._is_buffering = False
                else:
                    return None
            # Flatten needed chunks
            result = np.array([], dtype=np.int16)
            while len(result) < num_samples and self._chunks:
                chunk = self._chunks.popleft()
                result = np.concatenate((result, chunk))
            
            self._total_samples = sum(len(c) for c in self._chunks)
            
            if len(result) >= num_samples:
                output = result[:num_samples]
                leftover = result[num_samples:]
                if len(leftover) > 0:
                    self._chunks.appendleft(leftover)
                    self._total_samples += len(leftover)
                return output
            else:
                # Pad remaining
                output = np.pad(result, (0, num_samples - len(result)))
                self._is_buffering = True
                return output

    def clear(self) -> None:
        """Clear buffer on interruption or stop."""
        with self._lock:
            self._chunks.clear()
            self._total_samples = 0
            self._is_buffering = True

    def has_audio(self) -> bool:
        with self._lock:
            return self._total_samples > 0


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
        self._cached_ramp_len: int = 0
        self._cached_ramp: Optional[np.ndarray] = None

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
                target_gain = self.ducking_factor
                self.is_active = True
            else:
                target_gain = 1.0
                self.is_active = False

        # Calculate gain transition rates
        if target_gain < self.current_gain:
            rate_per_sec = (1.0 - self.ducking_factor) / (self.attack_ms / 1000.0)
            max_gain_delta = rate_per_sec * chunk_duration
            end_gain = max(target_gain, self.current_gain - max_gain_delta)
        else:
            rate_per_sec = (1.0 - self.ducking_factor) / (self.release_ms / 1000.0)
            max_gain_delta = rate_per_sec * chunk_duration
            end_gain = min(target_gain, self.current_gain + max_gain_delta)

        if chunk_len != self._cached_ramp_len:
            self._cached_ramp_len = chunk_len
        # Build ramp using np.linspace only when start/end gains differ significantly
        if abs(self.current_gain - end_gain) < 1e-6:
            gain_ramp = np.full(chunk_len, end_gain, dtype=np.float32)
        else:
            gain_ramp = np.linspace(self.current_gain, end_gain, chunk_len, dtype=np.float32)
        self.current_gain = end_gain

        bg_float = background_chunk.astype(np.float32)
        ducked_bg = bg_float * gain_ramp

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
    High-performance audio engine for bidirectional translation, sample playback, and mic testing.
    """

    def __init__(
        self,
        format_type: int = pyaudio.paInt16,
        channels: int = 1,
        rate: int = 16000,
        chunk_size: int = 512,
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

        # Mic testing stream
        self.mic_test_stream: Optional[pyaudio.Stream] = None

        # Input Queues for Gemini STT
        self.outgoing_input_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.incoming_input_queue: asyncio.Queue[bytes] = asyncio.Queue()

        # Audio Stream FIFO Buffers for Playback (Default 75ms low latency with fast-start)
        self.outgoing_playback_buffer = AudioStreamBuffer(sample_rate=rate, jitter_buffer_ms=75)
        self.incoming_playback_buffer = AudioStreamBuffer(sample_rate=rate, jitter_buffer_ms=75)

        # Mic Test Audio Collector (Recorded translated PCM)
        self.mic_test_recorded_pcm: List[np.ndarray] = []
        self.mic_test_file_path: Path = Path(__file__).parent / "samples" / "mic_test_result.wav"

        # Smart Ducking DSP Engines (Fast 25ms attack)
        self.incoming_ducking_dsp = SmartDuckingDSP(
            sample_rate=rate,
            ducking_factor=0.2,
            attack_ms=25.0,
            hold_ms=350.0,
            release_ms=150.0,
        )

        # Status flags
        self.is_call_running: bool = False
        self.is_dubbing_running: bool = False
        self.is_sample_running: bool = False
        self.is_mic_test_running: bool = False
        self.is_incoming_ducking: bool = False

        # Thread synchronization lock for PyAudio C-extension calls
        self._stream_lock: threading.Lock = threading.Lock()

        # Telemetry Callbacks
        self.outgoing_telemetry_cb: Optional[Callable[[float], None]] = None
        self.incoming_telemetry_cb: Optional[Callable[[float, bool], None]] = None

    def list_devices(self) -> List[Dict[str, str | int]]:
        """List all available audio input and output devices."""
        devices: List[Dict[str, str | int]] = []
        with self._stream_lock:
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
        self.incoming_ducking_dsp.set_ducking_factor(factor)

    def set_jitter_buffer_ms(self, ms: int) -> None:
        self.outgoing_playback_buffer.set_jitter_buffer_ms(ms)
        self.incoming_playback_buffer.set_jitter_buffer_ms(ms)

    def _calculate_rms_db(self, audio_data: np.ndarray) -> float:
        float_data = audio_data.astype(np.float32)
        rms = np.sqrt(np.mean(float_data**2))
        if rms > 0:
            return float(20 * np.log10(rms / 32767.0))
        return -100.0

    def _safe_read(self, stream: Optional[pyaudio.Stream], chunk_size: int) -> Optional[bytes]:
        """Safely read audio from PyAudio stream without artificial delay."""
        if stream is None:
            return None
        try:
            if stream.is_stopped() or not stream.is_active():
                return None
            return stream.read(chunk_size, exception_on_overflow=False)
        except Exception:
            return None

    def _safe_write(self, stream: Optional[pyaudio.Stream], data: bytes) -> bool:
        """Safely write audio data to PyAudio output stream."""
        if stream is None:
            return False
        try:
            if stream.is_stopped() or not stream.is_active():
                return False
            stream.write(data)
            return True
        except Exception:
            return False

    def _safe_close_stream(self, stream_attr: str) -> None:
        """Safely stop and close an audio stream protected by stream lock."""
        with self._stream_lock:
            stream = getattr(self, stream_attr, None)
            if stream is not None:
                try:
                    if stream.is_active():
                        stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
                setattr(self, stream_attr, None)

    def push_outgoing_tts_chunk(self, chunk: np.ndarray) -> None:
        self.outgoing_playback_buffer.push(chunk)
        if self.is_mic_test_running:
            self.mic_test_recorded_pcm.append(chunk)

    def push_incoming_tts_chunk(self, chunk: np.ndarray) -> None:
        self.incoming_playback_buffer.push(chunk)

    def clear_playback_buffers(self) -> None:
        self.outgoing_playback_buffer.clear()
        self.incoming_playback_buffer.clear()

    def start_call(
        self,
        my_mic_index: Optional[int] = None,
        call_virtual_mic_index: Optional[int] = None,
        call_input_index: Optional[int] = None,
        headphones_index: Optional[int] = None,
    ) -> None:
        if self.is_call_running:
            return

        self.clear_playback_buffers()

        with self._stream_lock:
            self.my_mic_stream = self.p.open(
                format=self.format_type,
                channels=self.channels,
                rate=self.rate,
                input=True,
                input_device_index=my_mic_index,
                frames_per_buffer=self.chunk_size,
            )

            if call_virtual_mic_index is not None:
                self.call_virtual_mic_stream = self.p.open(
                    format=self.format_type,
                    channels=self.channels,
                    rate=self.rate,
                    output=True,
                    output_device_index=call_virtual_mic_index,
                    frames_per_buffer=self.chunk_size,
                )

            if call_input_index is not None:
                self.call_input_stream = self.p.open(
                    format=self.format_type,
                    channels=self.channels,
                    rate=self.rate,
                    input=True,
                    input_device_index=call_input_index,
                    frames_per_buffer=self.chunk_size,
                )

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
        self.is_call_running = False
        time.sleep(0.03)  # Allow background executor tasks to exit read/write

        for stream_attr in [
            "my_mic_stream",
            "call_virtual_mic_stream",
            "call_input_stream",
            "headphones_stream",
        ]:
            self._safe_close_stream(stream_attr)

        self._drain_queues()
        self.clear_playback_buffers()

    def start_dubbing(
        self,
        input_device_index: Optional[int] = None,
        headphones_index: Optional[int] = None,
    ) -> None:
        if self.is_dubbing_running:
            return

        self.clear_playback_buffers()

        with self._stream_lock:
            if input_device_index is not None:
                self.call_input_stream = self.p.open(
                    format=self.format_type,
                    channels=self.channels,
                    rate=self.rate,
                    input=True,
                    input_device_index=input_device_index,
                    frames_per_buffer=self.chunk_size,
                )

            self.headphones_stream = self.p.open(
                format=self.format_type,
                channels=self.channels,
                rate=self.rate,
                output=True,
                output_device_index=headphones_index,
                frames_per_buffer=self.chunk_size,
            )

        self.is_dubbing_running = True

    def stop_dubbing(self) -> None:
        self.is_dubbing_running = False
        time.sleep(0.03)

        for stream_attr in [
            "call_input_stream",
            "headphones_stream",
        ]:
            self._safe_close_stream(stream_attr)

        self._drain_queues()
        self.clear_playback_buffers()

    def start_sample_test(self, headphones_index: Optional[int] = None) -> None:
        if self.is_sample_running:
            return

        self.clear_playback_buffers()

        with self._stream_lock:
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
        self.is_sample_running = False
        time.sleep(0.03)
        self._safe_close_stream("headphones_stream")
        self._drain_queues()
        self.clear_playback_buffers()

    def start_mic_test(self, mic_index: Optional[int] = None) -> None:
        """Start microphone test recording session."""
        if self.is_mic_test_running:
            return

        self.mic_test_recorded_pcm = []
        self.clear_playback_buffers()

        with self._stream_lock:
            self.mic_test_stream = self.p.open(
                format=self.format_type,
                channels=self.channels,
                rate=self.rate,
                input=True,
                input_device_index=mic_index,
                frames_per_buffer=self.chunk_size,
            )
        self.is_mic_test_running = True

    def stop_mic_test(self) -> Optional[str]:
        """Stop mic test recording and save translated WAV file."""
        self.is_mic_test_running = False
        time.sleep(0.03)
        self._safe_close_stream("mic_test_stream")
        self._drain_queues()

        # Save collected translated audio to WAV file
        if len(self.mic_test_recorded_pcm) > 0:
            full_audio = np.concatenate(self.mic_test_recorded_pcm)
            self.mic_test_file_path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(self.mic_test_file_path), "wb") as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(self.rate)
                wf.writeframes(full_audio.tobytes())
            return str(self.mic_test_file_path)
        return None

    def _drain_queues(self) -> None:
        for q in [self.outgoing_input_queue, self.incoming_input_queue]:
            while not q.empty():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    break

    async def outgoing_process_loop(self) -> None:
        loop = asyncio.get_running_loop()

        while self.is_call_running:
            if not self.my_mic_stream:
                await asyncio.sleep(0.01)
                continue

            try:
                raw_mic_bytes = await loop.run_in_executor(
                    None,
                    self._safe_read,
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

                if self.call_virtual_mic_stream:
                    tts_chunk = self.outgoing_playback_buffer.pop(self.chunk_size)
                    if tts_chunk is not None and self.is_call_running:
                        await loop.run_in_executor(
                            None,
                            self._safe_write,
                            self.call_virtual_mic_stream,
                            tts_chunk.tobytes(),
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Outgoing Loop Error] {e}")
                await asyncio.sleep(0.01)

    async def mic_test_loop(self) -> None:
        """Capture user voice during microphone test and stream to outgoing_ai."""
        loop = asyncio.get_running_loop()

        while self.is_mic_test_running:
            if not self.mic_test_stream:
                await asyncio.sleep(0.01)
                continue

            try:
                raw_mic_bytes = await loop.run_in_executor(
                    None,
                    self._safe_read,
                    self.mic_test_stream,
                    self.chunk_size,
                )

                if not raw_mic_bytes or not self.is_mic_test_running:
                    await asyncio.sleep(0.01)
                    continue

                await self.outgoing_input_queue.put(raw_mic_bytes)

                mic_audio = np.frombuffer(raw_mic_bytes, dtype=np.int16)
                if self.outgoing_telemetry_cb:
                    db = self._calculate_rms_db(mic_audio)
                    self.outgoing_telemetry_cb(db)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Mic Test Loop Error] {e}")
                await asyncio.sleep(0.01)

    async def incoming_process_loop(self) -> None:
        loop = asyncio.get_running_loop()

        while self.is_call_running or self.is_dubbing_running:
            if not self.call_input_stream or not self.headphones_stream:
                await asyncio.sleep(0.01)
                continue

            try:
                raw_call_bytes = await loop.run_in_executor(
                    None,
                    self._safe_read,
                    self.call_input_stream,
                    self.chunk_size,
                )

                if not raw_call_bytes or not (self.is_call_running or self.is_dubbing_running):
                    await asyncio.sleep(0.01)
                    continue

                await self.incoming_input_queue.put(raw_call_bytes)
                call_audio_chunk = np.frombuffer(raw_call_bytes, dtype=np.int16)

                voiceover_chunk = self.incoming_playback_buffer.pop(self.chunk_size)

                mixed_output, is_ducking = self.incoming_ducking_dsp.process(
                    call_audio_chunk, voiceover_chunk
                )
                self.is_incoming_ducking = is_ducking

                if self.incoming_telemetry_cb:
                    db = self._calculate_rms_db(call_audio_chunk)
                    self.incoming_telemetry_cb(db, self.is_incoming_ducking)

                if self.headphones_stream and (self.is_call_running or self.is_dubbing_running):
                    await loop.run_in_executor(
                        None,
                        self._safe_write,
                        self.headphones_stream,
                        mixed_output.tobytes(),
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Incoming Loop Error] {e}")
                await asyncio.sleep(0.01)

    async def sample_playback_loop(
        self,
        sample_filepath: str,
        ai_session_check: Optional[Callable[[], bool]] = None,
    ) -> None:
        """
        Feeds pre-recorded WAV sample into incoming AI pipeline and plays mixed Ukrainian voice to headphones.
        Includes turn completion drain to prevent cutting off the last phrases!
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
                            self._safe_write,
                            self.headphones_stream,
                            mixed_output.tobytes(),
                        )

                    await asyncio.sleep(chunk_duration_sec * 0.95)

                # Send 0.5s of silence frames so Gemini VAD cleanly marks end of speech
                silence_frame = np.zeros(self.chunk_size, dtype=np.int16).tobytes()
                for _ in range(8):
                    if not self.is_sample_running:
                        break
                    await self.incoming_input_queue.put(silence_frame)
                    await asyncio.sleep(chunk_duration_sec)

                # Intelligent completion drain:
                # Wait until Gemini finishes turn AND buffer is completely emptied to headphones
                max_drain_timeout = 10.0
                drain_start = time.time()
                last_active_time = time.time()

                while self.is_sample_running:
                    elapsed = time.time() - drain_start
                    if elapsed > max_drain_timeout:
                        break

                    # Check if playback buffer has voiceover
                    voiceover_chunk = self.incoming_playback_buffer.pop(self.chunk_size)
                    if voiceover_chunk is not None and np.any(np.abs(voiceover_chunk) > 30):
                        last_active_time = time.time()

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
                            self._safe_write,
                            self.headphones_stream,
                            mixed_output.tobytes(),
                        )

                    # If no new voiceover for 3.5s and buffer is empty
                    if (
                        time.time() - last_active_time > 3.5
                        and not self.incoming_playback_buffer.has_audio()
                    ):
                        break

                    await asyncio.sleep(chunk_duration_sec * 0.95)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[Sample Playback Error] {e}")
        finally:
            self.is_sample_running = False

    def terminate(self) -> None:
        """Cleanup PyAudio instance."""
        self.stop_call()
        self.stop_dubbing()
        self.stop_sample_test()
        self.stop_mic_test()
        with self._stream_lock:
            try:
                self.p.terminate()
            except Exception:
                pass

