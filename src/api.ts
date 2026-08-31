export interface AudioDevice {
  index: number;
  name: string;
  max_input_channels: number;
  max_output_channels: number;
  default_sample_rate: number;
}

export interface SampleInfo {
  id: string;
  title: string;
  category: string;
  description: string;
  filename: string;
}

export interface GeminiVoice {
  id: string;
  label: string;
  gender: "male" | "female";
}

export interface LogEntry {
  timestamp: string;
  level: "INFO" | "WARN" | "ERROR";
  message: string;
  source: string;
}

export interface StreamTelemetry {
  stt_text: string;
  translated_text: string;
  volume_db: number;
  is_ducking?: boolean;
}

export interface DualBackendState {
  is_call_active: boolean;
  is_testing_active: boolean;
  is_mic_test_active: boolean;
  active_sample_id: string | null;
  partner_lang: string;
  outgoing_voice: string;
  incoming_voice: string;
  jitter_buffer_ms: number;
  mic_test_latency_ms: number;
  last_error: string | null;
  logs: LogEntry[];
  outgoing: StreamTelemetry;
  incoming: StreamTelemetry;
}

export interface CallStartPayload {
  my_mic_index?: number;
  call_virtual_mic_index?: number;
  call_input_index?: number;
  headphones_index?: number;
  partner_lang: string;
  outgoing_voice: string;
  incoming_voice: string;
  ducking_factor: number;
  jitter_buffer_ms: number;
  api_key?: string;
}

export interface SampleStartPayload {
  sample_id: string;
  headphones_index?: number;
  ducking_factor: number;
  jitter_buffer_ms: number;
  partner_lang: string;
  voice_name: string;
  api_key?: string;
}

export interface MicTestStartPayload {
  mic_index?: number;
  partner_lang: string;
  voice_name: string;
  api_key?: string;
}

export interface MicTestResult {
  status: string;
  latency_ms: number;
  stt_text: string;
  translated_text: string;
  audio_url: string;
  has_audio: boolean;
}

const API_BASE = "http://127.0.0.1:8000";
const WS_URL = "ws://127.0.0.1:8000/ws";

export async function fetchAudioDevices(): Promise<AudioDevice[]> {
  try {
    const res = await fetch(`${API_BASE}/devices`);
    if (!res.ok) throw new Error("Failed to fetch devices");
    const data = await res.json();
    return data.devices;
  } catch (err) {
    console.error("[API] fetchAudioDevices error:", err);
    return [];
  }
}

export async function fetchVoices(): Promise<GeminiVoice[]> {
  try {
    const res = await fetch(`${API_BASE}/voices`);
    if (!res.ok) throw new Error("Failed to fetch voices");
    const data = await res.json();
    return data.voices;
  } catch (err) {
    console.error("[API] fetchVoices error:", err);
    return [];
  }
}

export async function fetchSamples(): Promise<SampleInfo[]> {
  try {
    const res = await fetch(`${API_BASE}/samples`);
    if (!res.ok) throw new Error("Failed to fetch samples");
    const data = await res.json();
    return data.samples;
  } catch (err) {
    console.error("[API] fetchSamples error:", err);
    return [];
  }
}

export async function fetchLogs(): Promise<LogEntry[]> {
  try {
    const res = await fetch(`${API_BASE}/logs`);
    if (!res.ok) throw new Error("Failed to fetch logs");
    const data = await res.json();
    return data.logs;
  } catch (err) {
    console.error("[API] fetchLogs error:", err);
    return [];
  }
}

export async function startCall(payload: CallStartPayload): Promise<void> {
  const res = await fetch(`${API_BASE}/call/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: "Failed to start call" }));
    throw new Error(errData.detail || "Failed to start call");
  }
}

export async function stopCall(): Promise<void> {
  const res = await fetch(`${API_BASE}/call/stop`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error("Failed to stop call");
  }
}

export async function startSampleTest(payload: SampleStartPayload): Promise<void> {
  const res = await fetch(`${API_BASE}/samples/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: "Failed to start sample test" }));
    throw new Error(errData.detail || "Failed to start sample test");
  }
}

export async function stopSampleTest(): Promise<void> {
  const res = await fetch(`${API_BASE}/samples/stop`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error("Failed to stop sample test");
  }
}

export async function startMicTest(payload: MicTestStartPayload): Promise<void> {
  const res = await fetch(`${API_BASE}/test_mic/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: "Failed to start mic test" }));
    throw new Error(errData.detail || "Failed to start mic test");
  }
}

export async function stopMicTest(): Promise<MicTestResult> {
  const res = await fetch(`${API_BASE}/test_mic/stop`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error("Failed to stop mic test");
  }
  return await res.json();
}

export async function updateDuckingFactor(ducking_factor: number): Promise<void> {
  await fetch(`${API_BASE}/ducking`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ducking_factor }),
  });
}

export async function updateJitterBuffer(jitter_buffer_ms: number): Promise<void> {
  await fetch(`${API_BASE}/jitter_buffer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jitter_buffer_ms }),
  });
}

export function subscribeToState(
  onState: (state: DualBackendState) => void
): () => void {
  let ws: WebSocket | null = null;
  let isClosing = false;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;

  const connect = () => {
    ws = new WebSocket(WS_URL);

    ws.onmessage = (event) => {
      try {
        const data: DualBackendState = JSON.parse(event.data);
        onState(data);
      } catch (err) {
        console.error("[WS] Parse error:", err);
      }
    };

    ws.onerror = (err) => {
      console.warn("[WS] Connection error:", err);
    };

    ws.onclose = () => {
      if (!isClosing) {
        retryTimer = setTimeout(connect, 1500);
      }
    };
  };

  connect();

  return () => {
    isClosing = true;
    if (retryTimer) clearTimeout(retryTimer);
    if (ws) ws.close();
  };
}
