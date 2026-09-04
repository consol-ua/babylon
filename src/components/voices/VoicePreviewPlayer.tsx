import React, { useState, useCallback, useRef, useEffect } from "react";
import { Play, Pause, Loader2, Volume2 } from "lucide-react";

export interface VoicePreviewPlayerProps {
  audioUrl?: string | null;
  onFetchAudio?: () => Promise<string>;
  label?: string;
  size?: "sm" | "md";
  className?: string;
}

export const VoicePreviewPlayer: React.FC<VoicePreviewPlayerProps> = React.memo(({
  audioUrl,
  onFetchAudio,
  label = "Прослухати",
  size = "sm",
  className = "",
}) => {
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [currentUrl, setCurrentUrl] = useState<string | null>(audioUrl || null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    setCurrentUrl(audioUrl || null);
  }, [audioUrl]);

  const stopAudio = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
    }
    setIsPlaying(false);
  }, []);

  const handleTogglePlay = useCallback(async () => {
    if (isPlaying) {
      stopAudio();
      return;
    }

    try {
      let targetUrl = currentUrl;

      if (!targetUrl && onFetchAudio) {
        setIsLoading(true);
        targetUrl = await onFetchAudio();
        setCurrentUrl(targetUrl);
      }

      if (!targetUrl) return;

      const audio = new Audio(targetUrl);
      audioRef.current = audio;
      setIsPlaying(true);

      audio.onended = () => {
        setIsPlaying(false);
        audioRef.current = null;
      };

      audio.onerror = () => {
        setIsPlaying(false);
        audioRef.current = null;
      };

      await audio.play();
    } catch (err) {
      console.error("[VoicePreviewPlayer] Playback error:", err);
      setIsPlaying(false);
    } finally {
      setIsLoading(false);
    }
  }, [isPlaying, currentUrl, onFetchAudio, stopAudio]);

  useEffect(() => {
    return () => {
      stopAudio();
    };
  }, [stopAudio]);

  const buttonPadding = size === "sm" ? "px-2 py-1 text-xs" : "px-3 py-1.5 text-sm";
  const iconSize = size === "sm" ? "w-3 h-3" : "w-4 h-4";

  return (
    <button
      type="button"
      onClick={() => void handleTogglePlay()}
      disabled={isLoading}
      className={`inline-flex items-center gap-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 transition-colors font-medium disabled:opacity-50 ${buttonPadding} ${className}`}
      title={label}
    >
      {isLoading ? (
        <Loader2 className={`${iconSize} animate-spin text-indigo-400`} />
      ) : isPlaying ? (
        <Pause className={`${iconSize} fill-current text-amber-400`} />
      ) : (
        <Play className={`${iconSize} fill-current text-indigo-400`} />
      )}
      <span>{label}</span>
      {isPlaying && <Volume2 className={`${iconSize} text-emerald-400 animate-pulse`} />}
    </button>
  );
});

VoicePreviewPlayer.displayName = "VoicePreviewPlayer";
