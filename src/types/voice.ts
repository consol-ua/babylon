/**
 * Domain types for Speech Synthesis (TTS) and Voice Cloning
 * Design Specification: docs/superpowers/specs/2026-09-04-local-tts-voice-cloning-design.md
 */

export type VoiceMode = "cloud" | "local" | "cloned";

export interface VoiceProfile {
  id: string;
  name: string;
  language: string;
  engine_type: "builtin" | "cloned";
  model_name?: string;
  reference_audio_path?: string;
  speaker_id?: number;
  created_at?: string;
}

export interface VoiceSelection {
  mode: VoiceMode;
  voice_id: string;
}

export interface CloudVoiceOption {
  id: string;
  label: string;
  gender?: string;
}

export interface LocalVoiceOption {
  id: string;
  name: string;
  language: string;
  description?: string;
}

export interface CategorizedVoices {
  cloud: Array<{ id: string; label: string; gender?: string }>;
  local: Array<{ id: string; name: string; language: string; description?: string }>;
  cloned: Array<VoiceProfile>;
}

export interface CreateVoiceProfilePayload {
  name: string;
  language: string;
  engine_type: "builtin" | "cloned";
  model_name?: string;
}

export interface TestSynthesizePayload {
  text: string;
  voice_id: string;
  mode: VoiceMode;
  language?: string;
}

export interface TestSynthesizeResponse {
  audio_url?: string;
  audio_base64?: string;
  status?: string;
  message?: string;
}
