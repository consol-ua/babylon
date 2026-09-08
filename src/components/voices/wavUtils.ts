/**
 * Utilities for client-side audio normalization, resampling, and WAV encoding.
 * Ensures consistent 16kHz 16-bit mono PCM across all browsers without external dependencies.
 */

/**
 * Encodes a Float32Array of audio samples into a standard 16-bit mono PCM WAV Blob.
 *
 * @param samples - Float32 audio samples in range [-1.0, 1.0]
 * @param sampleRate - Target sample rate in Hz (default: 16000)
 * @returns Blob with MIME type "audio/wav"
 */
export function encodeWav(samples: Float32Array, sampleRate: number = 16000): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  // RIFF header
  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(view, 8, "WAVE");

  // FMT sub-chunk
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true); // Subchunk1Size = 16 (PCM)
  view.setUint16(20, 1, true);  // AudioFormat = 1 (Linear PCM)
  view.setUint16(22, 1, true);  // NumChannels = 1 (Mono)
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // ByteRate = sampleRate * 1 * 2
  view.setUint16(32, 2, true);  // BlockAlign = 1 * 16 / 8 = 2
  view.setUint16(34, 16, true); // BitsPerSample = 16

  // Data sub-chunk
  writeString(view, 36, "data");
  view.setUint32(40, samples.length * 2, true);

  // Write 16-bit PCM samples with clipping
  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }

  return new Blob([view], { type: "audio/wav" });
}

function writeString(view: DataView, offset: number, string: string): void {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i));
  }
}

/**
 * Resamples input audio from origRate to targetRate using linear interpolation.
 */
export function resampleAudio(
  input: Float32Array,
  origRate: number,
  targetRate: number = 16000
): Float32Array {
  if (origRate === targetRate) {
    return input;
  }
  const ratio = origRate / targetRate;
  const newLength = Math.max(1, Math.round(input.length / ratio));
  const result = new Float32Array(newLength);

  for (let i = 0; i < newLength; i++) {
    const srcIndex = i * ratio;
    const i0 = Math.floor(srcIndex);
    const i1 = Math.min(i0 + 1, input.length - 1);
    const fraction = srcIndex - i0;
    result[i] = input[i0] * (1 - fraction) + input[i1] * fraction;
  }

  return result;
}

/**
 * Decodes any browser-supported audio file (MP3, M4A, OGG, WAV, FLAC, WebM)
 * down to 16kHz mono 16-bit PCM WAV.
 */
export async function convertFileTo16kWav(file: File): Promise<Blob> {
  const AudioCtx =
    window.AudioContext ||
    (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const ctx = new AudioCtx();

  try {
    const arrayBuffer = await file.arrayBuffer();
    const audioBuffer = await ctx.decodeAudioData(arrayBuffer);

    const numChannels = audioBuffer.numberOfChannels;
    const length = audioBuffer.length;
    const mono = new Float32Array(length);

    // Downmix multi-channel to mono
    for (let c = 0; c < numChannels; c++) {
      const channelData = audioBuffer.getChannelData(c);
      for (let i = 0; i < length; i++) {
        mono[i] += channelData[i] / numChannels;
      }
    }

    const resampled = resampleAudio(mono, audioBuffer.sampleRate, 16000);
    return encodeWav(resampled, 16000);
  } finally {
    if (ctx.state !== "closed") {
      void ctx.close().catch(() => {});
    }
  }
}
