import asyncio
import numpy as np
import pyaudio
from typing import List, Dict, Optional, Callable


class AudioEngine:
    """Core real-time audio routing and DSP mixing engine for macOS."""

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
        self.input_stream: Optional[pyaudio.Stream] = None
        self.output_stream: Optional[pyaudio.Stream] = None

        self.is_running: bool = False
        self.is_ducking_active: bool = False
        self.ducking_factor: float = 0.2  # Lower background audio to 20% by default

        # Audio Queues for asynchronous processing
        self.input_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.tts_playback_queue: asyncio.Queue[np.ndarray] = asyncio.Queue()

        # Telemetry callback (volume dB level, is_ducking)
        self.telemetry_callback: Optional[Callable[[float, bool], None]] = None

    def list_devices(self) -> List[Dict[str, str | int]]:
        """List all available audio input and output devices."""
        devices: List[Dict[str, str | int]] = []
        device_count = self.p.get_device_count()

        for i in range(device_count):
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
        return devices

    def set_ducking_factor(self, factor: float) -> None:
        """Set attenuation factor for ducking (0.0 = muted, 1.0 = full volume)."""
        self.ducking_factor = max(0.0, min(1.0, factor))

    def _apply_ducking_and_mix(
        self, background_chunk: np.ndarray, voiceover_chunk: Optional[np.ndarray]
    ) -> np.ndarray:
        """
        Applies sidechain compression (ducking) and mixes the voiceover with background audio.
        
        Math Explanation:
        - When voiceover is playing (is_ducking_active=True), attenuate the background 
          by multiplying its waveform amplitudes by `ducking_factor`.
        - Sum the two float arrays to mix signals.
        - Clip signal to prevent integer overflow/distortion [-32768, 32767] when casting back to int16.
        """
        bg_float = background_chunk.astype(np.float32)

        if voiceover_chunk is not None and len(voiceover_chunk) > 0:
            self.is_ducking_active = True
            # Attenuate background audio
            ducked_bg = bg_float * self.ducking_factor

            # Reshape or pad voiceover if sizes mismatch
            vo_float = voiceover_chunk.astype(np.float32)
            if len(vo_float) < len(ducked_bg):
                vo_float = np.pad(vo_float, (0, len(ducked_bg) - len(vo_float)))
            elif len(vo_float) > len(ducked_bg):
                vo_float = vo_float[: len(ducked_bg)]

            mixed = ducked_bg + vo_float
        else:
            self.is_ducking_active = False
            mixed = bg_float

        # Clip values to avoid clipping distortion
        mixed_clipped = np.clip(mixed, -32768, 32767).astype(np.int16)
        return mixed_clipped

    def _calculate_rms_db(self, audio_data: np.ndarray) -> float:
        """Calculates RMS volume level in decibels (dB)."""
        float_data = audio_data.astype(np.float32)
        rms = np.sqrt(np.mean(float_data**2))
        if rms > 0:
            return float(20 * np.log10(rms / 32767.0))
        return -100.0

    def start(
        self,
        input_device_index: Optional[int] = None,
        output_device_index: Optional[int] = None,
    ) -> None:
        """Start input and output audio streams."""
        if self.is_running:
            return

        self.input_stream = self.p.open(
            format=self.format_type,
            channels=self.channels,
            rate=self.rate,
            input=True,
            input_device_index=input_device_index,
            frames_per_buffer=self.chunk_size,
        )

        self.output_stream = self.p.open(
            format=self.format_type,
            channels=self.channels,
            rate=self.rate,
            output=True,
            output_device_index=output_device_index,
            frames_per_buffer=self.chunk_size,
        )

        self.is_running = True

    def stop(self) -> None:
        """Stop and close all audio streams."""
        self.is_running = False
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
            self.input_stream = None

        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
            self.output_stream = None

    async def process_loop(self) -> None:
        """Main async loop for reading, ducking, mixing, and writing audio buffers."""
        loop = asyncio.get_running_loop()

        while self.is_running:
            if not self.input_stream or not self.output_stream:
                await asyncio.sleep(0.01)
                continue

            try:
                # Read chunk from input device without blocking the async event loop
                raw_input_bytes = await loop.run_in_executor(
                    None,
                    self.input_stream.read,
                    self.chunk_size,
                    False,
                )

                # Push raw bytes to queue for Speech-To-Text processing
                await self.input_queue.put(raw_input_bytes)

                # Convert input to numpy array
                bg_audio_chunk = np.frombuffer(raw_input_bytes, dtype=np.int16)

                # Pop TTS voiceover chunk if available
                voiceover_chunk: Optional[np.ndarray] = None
                if not self.tts_playback_queue.empty():
                    voiceover_chunk = await self.tts_playback_queue.get()

                # Process ducking and mix
                output_chunk = self._apply_ducking_and_mix(
                    bg_audio_chunk, voiceover_chunk
                )

                # Calculate telemetry
                if self.telemetry_callback:
                    db = self._calculate_rms_db(bg_audio_chunk)
                    self.telemetry_callback(db, self.is_ducking_active)

                # Write mixed chunk to output speaker/device
                await loop.run_in_executor(
                    None, self.output_stream.write, output_chunk.tobytes()
                )

            except Exception as e:
                print(f"[AudioEngine Error] {e}")
                await asyncio.sleep(0.01)

    def terminate(self) -> None:
        """Cleanup PyAudio instance."""
        self.stop()
        self.p.terminate()
