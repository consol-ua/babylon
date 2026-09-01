import { GeminiVoice } from './api';

export interface LanguageOption {
  code: string;
  label: string;
}

export const SUPPORTED_LANGUAGES: LanguageOption[] = [
  { code: "en", label: "English (Англійська)" },
  { code: "de", label: "German (Німецька)" },
  { code: "pl", label: "Polish (Польська)" },
  { code: "es", label: "Spanish (Іспанська)" },
  { code: "fr", label: "French (Французька)" },
  { code: "it", label: "Italian (Італійська)" },
  { code: "ja", label: "Japanese (Японська)" },
  { code: "zh", label: "Chinese (Китайська)" },
];

export const DEFAULT_VOICES: GeminiVoice[] = [
  { id: "Puck", label: "Puck (Чоловічий / Енергійний, природний)", gender: "male" },
  { id: "Charon", label: "Charon (Чоловічий / Впевнений, спокійний)", gender: "male" },
  { id: "Fenrir", label: "Fenrir (Чоловічий / Низький тембр)", gender: "male" },
  { id: "Aoede", label: "Aoede (Жіночий / Виразний, глибокий)", gender: "female" },
  { id: "Kore", label: "Kore (Жіночий / Спокійний, м'який)", gender: "female" },
];

export const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000';
export const WS_URL = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000/ws';
