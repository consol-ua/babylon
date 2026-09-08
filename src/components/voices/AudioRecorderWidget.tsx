import React, { useState, useRef, useEffect, useCallback } from "react";
import {
  Mic,
  Square,
  Play,
  Pause,
  RotateCcw,
  Volume2,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";
import { encodeWav, resampleAudio } from "./wavUtils";

export interface AudioRecorderWidgetProps {
  onAudioRecorded: (blob: Blob, durationSeconds: number) => void;
  minDurationSeconds?: number;
  maxDurationSeconds?: number;
  disabled?: boolean;
  className?: string;
}

export const AudioRecorderWidget: React.FC<AudioRecorderWidgetProps> = React.memo(({
  onAudioRecorded,
  minDurationSeconds = 5,
  maxDurationSeconds = 10,
  disabled = false,
  className = "",
}) => {
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);
  const [volumeLevel, setVolumeLevel] = useState<number>(0); // 0 to 100%
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // References
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const scriptProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const timerIntervalRef = useRef<number | null>(null);
  const pcmChunksRef = useRef<Float32Array[]>([]);
  const isRecordingRef = useRef<boolean>(false);
  const startTimeRef = useRef<number>(0);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);

  // Clean up AudioContext & MediaStream
  const cleanupAudio = useCallback(() => {
    isRecordingRef.current = false;
    if (animFrameRef.current !== null) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (timerIntervalRef.current !== null) {
      window.clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
    if (scriptProcessorRef.current) {
      try {
        scriptProcessorRef.current.disconnect();
      } catch {
        // ignore
      }
      scriptProcessorRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    if (audioContextRef.current && audioContextRef.current.state !== "closed") {
      void audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    analyserRef.current = null;
    setVolumeLevel(0);
  }, []);

  // Format seconds as MM:SS (e.g. "0:07")
  const formatTime = useCallback((totalSeconds: number): string => {
    const mins = Math.floor(totalSeconds / 60);
    const secs = Math.floor(totalSeconds % 60);
    return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
  }, []);

  // Stop recording handler
  const stopRecording = useCallback(() => {
    if (!isRecordingRef.current) return;
    isRecordingRef.current = false;
    setIsRecording(false);

    const finalDuration = Math.max(0.1, (performance.now() - startTimeRef.current) / 1000);
    const audioCtx = audioContextRef.current;
    const sampleRate = audioCtx ? audioCtx.sampleRate : 16000;

    // Flatten collected Float32 PCM chunks
    const chunks = pcmChunksRef.current;
    let totalSamples = 0;
    for (let i = 0; i < chunks.length; i++) {
      totalSamples += chunks[i].length;
    }

    if (totalSamples > 0) {
      const merged = new Float32Array(totalSamples);
      let offset = 0;
      for (let i = 0; i < chunks.length; i++) {
        merged.set(chunks[i], offset);
        offset += chunks[i].length;
      }

      // Resample down to pristine 16kHz mono and encode into RIFF WAV Blob
      const resampled = resampleAudio(merged, sampleRate, 16000);
      const wavBlob = encodeWav(resampled, 16000);
      setRecordedBlob(wavBlob);
      const url = URL.createObjectURL(wavBlob);
      setAudioUrl(url);
      onAudioRecorded(wavBlob, Math.round(finalDuration * 10) / 10);
    }

    cleanupAudio();
  }, [cleanupAudio, onAudioRecorded]);

  // Start recording
  const startRecording = useCallback(async () => {
    setErrorMessage(null);
    setRecordedBlob(null);
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
      setAudioUrl(null);
    }
    pcmChunksRef.current = [];
    setElapsedSeconds(0);

    try {
      // 1. Acquire mic stream with graceful fallback constraints
      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: { ideal: 1 },
            sampleRate: { ideal: 16000 },
            echoCancellation: false,
            noiseSuppression: false,
            autoGainControl: false,
          },
        });
      } catch {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      }
      mediaStreamRef.current = stream;

      // 2. Set up Web Audio Context & analyzer
      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const audioCtx = new AudioCtx();
      audioContextRef.current = audioCtx;

      const sourceNode = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.7;
      sourceNode.connect(analyser);
      analyserRef.current = analyser;

      // 3. Set up ScriptProcessor for direct uncompressed PCM capture
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
      scriptProcessorRef.current = processor;
      processor.onaudioprocess = (e: AudioProcessingEvent) => {
        if (!isRecordingRef.current) return;
        const channel = e.inputBuffer.getChannelData(0);
        pcmChunksRef.current.push(new Float32Array(channel));
      };
      sourceNode.connect(processor);
      processor.connect(audioCtx.destination);

      // 4. Volume meter render loop
      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      const updateVolumeLoop = () => {
        if (!analyserRef.current) return;
        analyserRef.current.getByteFrequencyData(dataArray);

        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i];
        }
        const avg = sum / dataArray.length;
        const levelPct = Math.min(100, Math.round((avg / 120) * 100));
        setVolumeLevel(levelPct);

        animFrameRef.current = requestAnimationFrame(updateVolumeLoop);
      };
      animFrameRef.current = requestAnimationFrame(updateVolumeLoop);

      // 5. Start timer and mark recording active
      isRecordingRef.current = true;
      startTimeRef.current = performance.now();
      setIsRecording(true);

      timerIntervalRef.current = window.setInterval(() => {
        const currentElapsed = (performance.now() - startTimeRef.current) / 1000;
        setElapsedSeconds(currentElapsed);

        if (currentElapsed >= maxDurationSeconds) {
          stopRecording();
        }
      }, 100);
    } catch (err) {
      console.error("[AudioRecorderWidget] Failed to access microphone:", err);
      setErrorMessage(
        "Не вдалося отримати доступ до мікрофона. Перевірте дозволи браузера на запис аудіо."
      );
      cleanupAudio();
      setIsRecording(false);
    }
  }, [maxDurationSeconds, cleanupAudio, stopRecording, audioUrl]);


  // Handle Play / Pause of recorded preview
  const togglePlayRecorded = useCallback(() => {
    if (!audioUrl) return;

    if (isPlaying) {
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause();
        audioPlayerRef.current.currentTime = 0;
      }
      setIsPlaying(false);
    } else {
      const audio = new Audio(audioUrl);
      audioPlayerRef.current = audio;
      setIsPlaying(true);

      audio.onended = () => {
        setIsPlaying(false);
        audioPlayerRef.current = null;
      };

      audio.onerror = () => {
        setIsPlaying(false);
        audioPlayerRef.current = null;
      };

      void audio.play().catch(() => {
        setIsPlaying(false);
        audioPlayerRef.current = null;
      });
    }
  }, [audioUrl, isPlaying]);

  // Reset / Re-record
  const handleReset = useCallback(() => {
    if (isPlaying && audioPlayerRef.current) {
      audioPlayerRef.current.pause();
      audioPlayerRef.current = null;
      setIsPlaying(false);
    }
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
    }
    setRecordedBlob(null);
    setAudioUrl(null);
    setElapsedSeconds(0);
    setVolumeLevel(0);
    setErrorMessage(null);
  }, [isPlaying, audioUrl]);

  // Component unmount cleanup
  useEffect(() => {
    return () => {
      cleanupAudio();
      if (audioPlayerRef.current) {
        audioPlayerRef.current.pause();
        audioPlayerRef.current = null;
      }
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
    };
  }, [cleanupAudio, audioUrl]);

  const durationStatus = recordedBlob
    ? elapsedSeconds >= minDurationSeconds
      ? "optimal"
      : "short"
    : null;

  return (
    <div
      className={`bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-3.5 ${className}`}
    >
      {/* Header with Title & Timer */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div
            className={`p-1.5 rounded-lg ${
              isRecording
                ? "bg-rose-500/20 text-rose-400 animate-pulse"
                : recordedBlob
                ? "bg-emerald-500/20 text-emerald-400"
                : "bg-slate-800 text-slate-400"
            }`}
          >
            <Mic className="w-4 h-4" />
          </div>
          <div>
            <span className="text-xs font-semibold text-slate-200">
              {isRecording
                ? "Йде запис голосу..."
                : recordedBlob
                ? "Зразок голосу записано"
                : "Запис 5-10 секундного зразка"}
            </span>
            <p className="text-[11px] text-slate-400">
              Говоріть у мікрофон природним тоном (5–10 сек)
            </p>
          </div>
        </div>

        {/* Timer Display */}
        <div className="font-mono text-xs font-medium px-2.5 py-1 rounded-md bg-slate-900 border border-slate-800 text-slate-300">
          <span className={isRecording ? "text-rose-400 font-bold" : ""}>
            {formatTime(elapsedSeconds)}
          </span>
          <span className="text-slate-500"> / {formatTime(maxDurationSeconds)}</span>
        </div>
      </div>

      {/* Live VU / Volume Meter */}
      <div className="space-y-1.5">
        <div className="flex justify-between items-center text-[11px] text-slate-400">
          <span className="flex items-center gap-1">
            <Volume2 className="w-3 h-3 text-indigo-400" />
            Рівень сигналу мікрофона
          </span>
          <span className="font-mono text-[10px] text-slate-500">{volumeLevel}%</span>
        </div>
        <div className="w-full bg-slate-900 h-2.5 rounded-full overflow-hidden border border-slate-800 p-0.5">
          <div
            className={`h-full rounded-full transition-all duration-75 ${
              isRecording
                ? volumeLevel > 80
                  ? "bg-gradient-to-r from-emerald-500 via-amber-500 to-rose-500"
                  : "bg-gradient-to-r from-indigo-500 to-emerald-400"
                : "bg-slate-800"
            }`}
            style={{ width: `${Math.max(2, volumeLevel)}%` }}
          />
        </div>
      </div>

      {/* Progress Track for Recording Duration */}
      {isRecording && (
        <div className="space-y-1">
          <div className="w-full bg-slate-900 h-1.5 rounded-full overflow-hidden">
            <div
              className="h-full bg-rose-500 transition-all duration-100 ease-linear"
              style={{ width: `${Math.min(100, (elapsedSeconds / maxDurationSeconds) * 100)}%` }}
            />
          </div>
          <div className="flex justify-between text-[10px] text-slate-500 px-0.5">
            <span>0s</span>
            <span className="text-amber-400/80 font-medium">Мін: {minDurationSeconds}s</span>
            <span>Макс: {maxDurationSeconds}s</span>
          </div>
        </div>
      )}

      {/* Error Message */}
      {errorMessage && (
        <div className="flex items-center gap-2 p-2 rounded-lg bg-rose-950/50 border border-rose-800/50 text-rose-300 text-xs">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Duration Quality Status */}
      {durationStatus && (
        <div
          className={`flex items-center gap-2 p-2 rounded-lg text-xs ${
            durationStatus === "optimal"
              ? "bg-emerald-950/40 border border-emerald-800/50 text-emerald-300"
              : "bg-amber-950/40 border border-amber-800/50 text-amber-300"
          }`}
        >
          {durationStatus === "optimal" ? (
            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0 text-amber-400" />
          )}
          <span>
            {durationStatus === "optimal"
              ? `Чудово! Записано ${elapsedSeconds.toFixed(1)} с. Тривалість оптимальна для синтезу.`
              : `Увага: Записано лише ${elapsedSeconds.toFixed(1)} с (рекомендовано від ${minDurationSeconds} с).`}
          </span>
        </div>
      )}

      {/* Control Buttons */}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        {!isRecording && !recordedBlob && (
          <button
            type="button"
            onClick={() => void startRecording()}
            disabled={disabled}
            className="flex-1 flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 text-white px-4 py-2 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
          >
            <span className="w-2.5 h-2.5 rounded-full bg-rose-400 animate-ping" />
            Почати запис (5-10с)
          </button>
        )}

        {isRecording && (
          <button
            type="button"
            onClick={stopRecording}
            className="flex-1 flex items-center justify-center gap-2 bg-rose-600 hover:bg-rose-500 active:bg-rose-700 text-white px-4 py-2 rounded-lg text-xs font-semibold transition-colors shadow-sm animate-pulse"
          >
            <Square className="w-3.5 h-3.5 fill-current" />
            Зупинити запис
          </button>
        )}

        {recordedBlob && !isRecording && (
          <>
            <button
              type="button"
              onClick={togglePlayRecorded}
              className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-colors shadow-sm ${
                isPlaying
                  ? "bg-amber-600 hover:bg-amber-500 text-white"
                  : "bg-emerald-600 hover:bg-emerald-500 text-white"
              }`}
            >
              {isPlaying ? (
                <>
                  <Pause className="w-3.5 h-3.5 fill-current" />
                  Пауза
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 fill-current" />
                  Прослухати зразок
                </>
              )}
            </button>

            <button
              type="button"
              onClick={handleReset}
              disabled={disabled}
              className="flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-2 rounded-lg text-xs font-medium transition-colors border border-slate-700 disabled:opacity-50"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Перезаписати
            </button>
          </>
        )}
      </div>
    </div>
  );
});

AudioRecorderWidget.displayName = "AudioRecorderWidget";
