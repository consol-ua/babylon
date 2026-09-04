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
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const timerIntervalRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startTimeRef = useRef<number>(0);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);

  // Clean up AudioContext & MediaStream
  const cleanupAudio = useCallback(() => {
    if (animFrameRef.current !== null) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (timerIntervalRef.current !== null) {
      window.clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
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
    if (!isRecording) return;
    setIsRecording(false);

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    cleanupAudio();
  }, [isRecording, cleanupAudio]);

  // Start recording
  const startRecording = useCallback(async () => {
    setErrorMessage(null);
    setRecordedBlob(null);
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
      setAudioUrl(null);
    }
    chunksRef.current = [];
    setElapsedSeconds(0);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      });
      mediaStreamRef.current = stream;

      // Select supported MIME type
      let mimeType = "audio/webm;codecs=opus";
      if (typeof MediaRecorder !== "undefined") {
        if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
          mimeType = "audio/webm;codecs=opus";
        } else if (MediaRecorder.isTypeSupported("audio/webm")) {
          mimeType = "audio/webm";
        } else if (MediaRecorder.isTypeSupported("audio/mp4")) {
          mimeType = "audio/mp4";
        } else if (MediaRecorder.isTypeSupported("audio/wav")) {
          mimeType = "audio/wav";
        }
      }

      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e: BlobEvent) => {
        if (e.data && e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      recorder.onstop = () => {
        const finalDuration = (performance.now() - startTimeRef.current) / 1000;
        const blob = new Blob(chunksRef.current, { type: mimeType });
        setRecordedBlob(blob);
        const url = URL.createObjectURL(blob);
        setAudioUrl(url);
        onAudioRecorded(blob, Math.round(finalDuration * 10) / 10);
      };

      // Set up Web Audio API Volume Analyzer
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

      const dataArray = new Uint8Array(analyser.frequencyBinCount);

      const updateVolumeLoop = () => {
        if (!analyserRef.current) return;
        analyserRef.current.getByteFrequencyData(dataArray);

        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sum += dataArray[i];
        }
        const avg = sum / dataArray.length;
        // Normalize 0-255 to 0-100% with a sensible perceptual curve
        const levelPct = Math.min(100, Math.round((avg / 120) * 100));
        setVolumeLevel(levelPct);

        animFrameRef.current = requestAnimationFrame(updateVolumeLoop);
      };
      animFrameRef.current = requestAnimationFrame(updateVolumeLoop);

      // Start Recorder
      recorder.start(100);
      startTimeRef.current = performance.now();
      setIsRecording(true);

      // Timer Interval
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
  }, [maxDurationSeconds, onAudioRecorded, stopRecording, cleanupAudio, audioUrl]);

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
