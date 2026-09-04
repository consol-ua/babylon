import { useState, useEffect, useCallback, useRef } from "react";
import { API_BASE, DEFAULT_VOICES } from "../constants";
import {
  CategorizedVoices,
  CreateVoiceProfilePayload,
  TestSynthesizePayload,
  VoiceProfile,
} from "../types/voice";

const DEFAULT_LOCAL_VOICES = [
  {
    id: "uk_lada",
    name: "Лада (uk_UA)",
    language: "uk",
    description: "Piper TTS (Fast ONNX, природна інтонація)",
  },
  {
    id: "en_lessac",
    name: "Lessac (en_US)",
    language: "en",
    description: "Piper TTS (Fast ONNX, чітка англійська вимова)",
  },
  {
    id: "en_ryan",
    name: "Ryan (en_US)",
    language: "en",
    description: "Piper TTS (Fast ONNX, чоловічий голос)",
  },
];

const INITIAL_CATEGORIZED_VOICES: CategorizedVoices = {
  cloud: DEFAULT_VOICES.map((v) => ({
    id: v.id,
    label: v.label,
    gender: v.gender,
  })),
  local: DEFAULT_LOCAL_VOICES,
  cloned: [],
};

export interface UseVoiceProfilesResult {
  categorizedVoices: CategorizedVoices;
  profiles: VoiceProfile[];
  isLoading: boolean;
  isSynthesizing: boolean;
  isPlaying: boolean;
  error: string | null;
  refreshVoices: () => Promise<void>;
  createProfile: (payload: CreateVoiceProfilePayload) => Promise<VoiceProfile>;
  uploadSample: (profileId: string, audio: File | Blob, filename?: string) => Promise<VoiceProfile>;
  recordSample: (profileId: string, durationSeconds?: number, micIndex?: number) => Promise<VoiceProfile>;
  deleteProfile: (profileId: string) => Promise<void>;
  testSynthesize: (payload: TestSynthesizePayload) => Promise<{ audioUrl: string }>;
  playAudio: (audioUrlOrBlob: string | Blob) => Promise<void>;
  stopPlayback: () => void;
}

export function useVoiceProfiles(): UseVoiceProfilesResult {
  const [categorizedVoices, setCategorizedVoices] = useState<CategorizedVoices>(INITIAL_CATEGORIZED_VOICES);
  const [profiles, setProfiles] = useState<VoiceProfile[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isSynthesizing, setIsSynthesizing] = useState<boolean>(false);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);
  const activeBlobUrlRef = useRef<string | null>(null);

  // Stop and clean up audio element
  const stopPlayback = useCallback(() => {
    if (audioPlayerRef.current) {
      audioPlayerRef.current.pause();
      audioPlayerRef.current.currentTime = 0;
      audioPlayerRef.current = null;
    }
    setIsPlaying(false);
  }, []);

  // Play audio url or Blob
  const playAudio = useCallback(async (audioUrlOrBlob: string | Blob): Promise<void> => {
    stopPlayback();

    let url: string;
    if (typeof audioUrlOrBlob === "string") {
      url = audioUrlOrBlob;
    } else {
      if (activeBlobUrlRef.current) {
        URL.revokeObjectURL(activeBlobUrlRef.current);
      }
      url = URL.createObjectURL(audioUrlOrBlob);
      activeBlobUrlRef.current = url;
    }

    return new Promise<void>((resolve, reject) => {
      const audio = new Audio(url);
      audioPlayerRef.current = audio;
      setIsPlaying(true);

      audio.onended = () => {
        setIsPlaying(false);
        audioPlayerRef.current = null;
        resolve();
      };

      audio.onerror = () => {
        setIsPlaying(false);
        audioPlayerRef.current = null;
        reject(new Error("Audio playback failed"));
      };

      audio.play().catch((err: unknown) => {
        setIsPlaying(false);
        audioPlayerRef.current = null;
        reject(err instanceof Error ? err : new Error(String(err)));
      });
    });
  }, [stopPlayback]);

  // Load categorized voices and custom profiles from backend
  const refreshVoices = useCallback(async (): Promise<void> => {
    setIsLoading(true);
    setError(null);

    try {
      // 1. Fetch categorized options
      let fetchedOptions: Partial<CategorizedVoices> | null = null;
      try {
        const optionsRes = await fetch(`${API_BASE}/api/voices/options`);
        if (optionsRes.ok) {
          fetchedOptions = (await optionsRes.json()) as Partial<CategorizedVoices> & {
            builtin?: Array<{ id: string; name: string; language: string; description?: string }>;
          };
        }
      } catch (err) {
        console.warn("[useVoiceProfiles] /api/voices/options request failed, using defaults:", err);
      }

      // 2. Fetch user custom profiles
      let fetchedProfiles: VoiceProfile[] = [];
      try {
        const profilesRes = await fetch(`${API_BASE}/api/voice-profiles`);
        if (profilesRes.ok) {
          const data = (await profilesRes.json()) as { profiles?: VoiceProfile[] } | VoiceProfile[];
          if (Array.isArray(data)) {
            fetchedProfiles = data;
          } else if (Array.isArray(data.profiles)) {
            fetchedProfiles = data.profiles;
          }
        }
      } catch (err) {
        console.warn("[useVoiceProfiles] /api/voice-profiles request failed:", err);
      }

      setProfiles(fetchedProfiles);

      setCategorizedVoices((prev) => {
        const rawOptions = fetchedOptions as
          | (Partial<CategorizedVoices> & {
              builtin?: Array<{ id: string; name: string; language: string; description?: string }>;
            })
          | null;

        const cloud = rawOptions?.cloud && rawOptions.cloud.length > 0 ? rawOptions.cloud : prev.cloud;
        const local =
          rawOptions?.local && rawOptions.local.length > 0
            ? rawOptions.local
            : rawOptions?.builtin && rawOptions.builtin.length > 0
            ? rawOptions.builtin
            : prev.local;
        const cloned =
          fetchedProfiles.length > 0
            ? fetchedProfiles
            : rawOptions?.cloned && rawOptions.cloned.length > 0
            ? rawOptions.cloned
            : prev.cloned;

        return {
          cloud,
          local,
          cloned,
        };
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load voices";
      setError(msg);
      console.error("[useVoiceProfiles] refreshVoices error:", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    void refreshVoices();

    return () => {
      stopPlayback();
      if (activeBlobUrlRef.current) {
        URL.revokeObjectURL(activeBlobUrlRef.current);
        activeBlobUrlRef.current = null;
      }
    };
  }, [refreshVoices, stopPlayback]);

  // Create a new voice profile
  const createProfile = useCallback(
    async (payload: CreateVoiceProfilePayload): Promise<VoiceProfile> => {
      setIsLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/api/voice-profiles`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        if (!res.ok) {
          const errData = (await res.json().catch(() => ({}))) as { detail?: string };
          throw new Error(errData.detail || "Failed to create voice profile");
        }

        const newProfile = (await res.json()) as VoiceProfile;

        // Update local state
        setProfiles((prev) => [...prev, newProfile]);
        setCategorizedVoices((prev) => ({
          ...prev,
          cloned: [...prev.cloned, newProfile],
        }));

        return newProfile;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to create profile";
        setError(msg);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  // Upload an audio sample to a voice profile
  const uploadSample = useCallback(
    async (profileId: string, audio: File | Blob, filename?: string): Promise<VoiceProfile> => {
      setIsLoading(true);
      setError(null);
      try {
        const formData = new FormData();
        const fileToUpload =
          audio instanceof File
            ? audio
            : new File([audio], filename || `sample_${profileId}.wav`, {
                type: audio.type || "audio/wav",
              });
        formData.append("file", fileToUpload);

        const res = await fetch(`${API_BASE}/api/voice-profiles/${encodeURIComponent(profileId)}/upload-sample`, {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          const errData = (await res.json().catch(() => ({}))) as { detail?: string };
          throw new Error(errData.detail || "Failed to upload reference sample");
        }

        const updatedProfile = (await res.json()) as VoiceProfile;

        // Update local states
        setProfiles((prev) => prev.map((p) => (p.id === profileId ? updatedProfile : p)));
        setCategorizedVoices((prev) => ({
          ...prev,
          cloned: prev.cloned.map((p) => (p.id === profileId ? updatedProfile : p)),
        }));

        return updatedProfile;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to upload audio sample";
        setError(msg);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  // Trigger microphone capture on backend
  const recordSample = useCallback(
    async (profileId: string, durationSeconds: number = 7, micIndex?: number): Promise<VoiceProfile> => {
      setIsLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/api/voice-profiles/${encodeURIComponent(profileId)}/record-sample`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            duration: durationSeconds,
            mic_index: micIndex,
          }),
        });

        if (!res.ok) {
          const errData = (await res.json().catch(() => ({}))) as { detail?: string };
          throw new Error(errData.detail || "Failed to record audio sample on server");
        }

        const updatedProfile = (await res.json()) as VoiceProfile;

        setProfiles((prev) => prev.map((p) => (p.id === profileId ? updatedProfile : p)));
        setCategorizedVoices((prev) => ({
          ...prev,
          cloned: prev.cloned.map((p) => (p.id === profileId ? updatedProfile : p)),
        }));

        return updatedProfile;
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to record audio sample";
        setError(msg);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  // Delete a voice profile
  const deleteProfile = useCallback(
    async (profileId: string): Promise<void> => {
      setIsLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/api/voice-profiles/${encodeURIComponent(profileId)}`, {
          method: "DELETE",
        });

        if (!res.ok) {
          const errData = (await res.json().catch(() => ({}))) as { detail?: string };
          throw new Error(errData.detail || "Failed to delete profile");
        }

        setProfiles((prev) => prev.filter((p) => p.id !== profileId));
        setCategorizedVoices((prev) => ({
          ...prev,
          cloned: prev.cloned.filter((p) => p.id !== profileId),
        }));
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to delete voice profile";
        setError(msg);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  // Test synthesize phrase
  const testSynthesize = useCallback(
    async (payload: TestSynthesizePayload): Promise<{ audioUrl: string }> => {
      setIsSynthesizing(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/api/voice-profiles/test-synthesize`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        if (!res.ok) {
          const errData = (await res.json().catch(() => ({}))) as { detail?: string };
          throw new Error(errData.detail || "Test synthesis failed");
        }

        const contentType = res.headers.get("content-type") || "";

        if (contentType.includes("audio/") || contentType.includes("application/octet-stream")) {
          const blob = await res.blob();
          if (activeBlobUrlRef.current) {
            URL.revokeObjectURL(activeBlobUrlRef.current);
          }
          const audioUrl = URL.createObjectURL(blob);
          activeBlobUrlRef.current = audioUrl;
          return { audioUrl };
        }

        // Otherwise JSON response
        const data = (await res.json()) as {
          audio_url?: string;
          audio_base64?: string;
          detail?: string;
        };

        if (data.audio_base64) {
          const audioUrl = `data:audio/wav;base64,${data.audio_base64}`;
          return { audioUrl };
        }

        if (data.audio_url) {
          const audioUrl = data.audio_url.startsWith("http")
            ? data.audio_url
            : `${API_BASE}${data.audio_url}`;
          return { audioUrl };
        }

        throw new Error(data.detail || "Synthesis returned no audio data");
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Test synthesis failed";
        setError(msg);
        throw err;
      } finally {
        setIsSynthesizing(false);
      }
    },
    []
  );

  return {
    categorizedVoices,
    profiles,
    isLoading,
    isSynthesizing,
    isPlaying,
    error,
    refreshVoices,
    createProfile,
    uploadSample,
    recordSample,
    deleteProfile,
    testSynthesize,
    playAudio,
    stopPlayback,
  };
}
