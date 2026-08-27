export interface AudioDevice {
  index: number;
  name: string;
  max_input_channels: number;
  max_output_channels: number;
  default_sample_rate: number;
}

export interface BackendState {
  is_translating: boolean;
  stt_text: string;
  translated_text: string;
  volume_db: number;
  is_ducking: boolean;
}

const BACKEND_URL = "http://localhost:8000";
const WS_URL = "ws://localhost:8000/ws";

export async function fetchAudioDevices(): Promise<AudioDevice[]> {
  try {
    const res = await fetch(`${BACKEND_URL}/devices`);
    if (!res.ok) throw new Error("Failed to fetch devices");
    const data = await res.json();
    return data.devices;
  } catch (err) {
    console.error("API error fetchAudioDevices:", err);
    return [];
  }
}

export async function startTranslation(
  inputDeviceIndex?: number,
  outputDeviceIndex?: number,
  targetLang: string = "uk",
  apiKey?: string
): Promise<boolean> {
  try {
    const res = await fetch(`${BACKEND_URL}/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        input_device_index: inputDeviceIndex,
        output_device_index: outputDeviceIndex,
        target_lang: targetLang,
        api_key: apiKey || undefined,
      }),
    });
    return res.ok;
  } catch (err) {
    console.error("API error startTranslation:", err);
    return false;
  }
}

export async function stopTranslation(): Promise<boolean> {
  try {
    const res = await fetch(`${BACKEND_URL}/stop`, { method: "POST" });
    return res.ok;
  } catch (err) {
    console.error("API error stopTranslation:", err);
    return false;
  }
}

export async function updateDuckingFactor(factor: number): Promise<boolean> {
  try {
    const res = await fetch(`${BACKEND_URL}/ducking`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ducking_factor: factor }),
    });
    return res.ok;
  } catch (err) {
    console.error("API error updateDuckingFactor:", err);
    return false;
  }
}

export function subscribeToState(
  onStateUpdate: (state: BackendState) => void
): () => void {
  let ws: WebSocket | null = null;
  let isClosedManually = false;

  const connect = () => {
    ws = new WebSocket(WS_URL);

    ws.onmessage = (event) => {
      try {
        const data: BackendState = JSON.parse(event.data);
        onStateUpdate(data);
      } catch (err) {
        console.error("Failed to parse websocket message:", err);
      }
    };

    ws.onclose = () => {
      if (!isClosedManually) {
        setTimeout(connect, 1000);
      }
    };

    ws.onerror = (err) => {
      console.warn("WebSocket error:", err);
      ws?.close();
    };
  };

  connect();

  return () => {
    isClosedManually = true;
    ws?.close();
  };
}
