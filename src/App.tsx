import React, { useEffect, useState, useCallback } from "react";
import {
  fetchAudioDevices,
  startTranslation,
  stopTranslation,
  updateDuckingFactor,
  subscribeToState,
  AudioDevice,
  BackendState,
} from "./api";
import { Mic, Volume2, Radio, Activity, VolumeX, Play, Square } from "lucide-react";

export const App: React.FC = () => {
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [selectedInput, setSelectedInput] = useState<number | undefined>();
  const [selectedOutput, setSelectedOutput] = useState<number | undefined>();
  const [duckingFactor, setDuckingFactor] = useState<number>(0.2);

  const [backendState, setBackendState] = useState<BackendState>({
    is_translating: false,
    stt_text: "",
    translated_text: "",
    volume_db: -100,
    is_ducking: false,
  });

  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Fetch audio input/output devices on mount
  useEffect(() => {
    fetchAudioDevices().then((devs) => {
      setDevices(devs);
      const defaultIn = devs.find((d) => d.max_input_channels > 0);
      const defaultOut = devs.find((d) => d.max_output_channels > 0);
      if (defaultIn) setSelectedInput(defaultIn.index);
      if (defaultOut) setSelectedOutput(defaultOut.index);
    });

    const unsubscribe = subscribeToState((newState) => {
      setBackendState(newState);
    });

    return () => {
      unsubscribe();
    };
  }, []);

  const handleToggleTranslation = useCallback(async () => {
    setIsLoading(true);
    try {
      if (backendState.is_translating) {
        await stopTranslation();
      } else {
        await startTranslation(selectedInput, selectedOutput, "en-US", "uk");
      }
    } finally {
      setIsLoading(false);
    }
  }, [backendState.is_translating, selectedInput, selectedOutput]);

  const handleDuckingChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = parseFloat(e.target.value);
      setDuckingFactor(val);
      await updateDuckingFactor(val);
    },
    []
  );

  const inputDevices = devices.filter((d) => d.max_input_channels > 0);
  const outputDevices = devices.filter((d) => d.max_output_channels > 0);

  // Normalize dB value for VU meter [ -60dB -> 0dB ] => [ 0% -> 100% ]
  const volumePercentage = Math.max(
    0,
    Math.min(100, ((backendState.volume_db + 60) / 60) * 100)
  );

  return (
    <div className="flex flex-col min-h-screen bg-slate-950 text-slate-100 p-6 space-y-6">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-wide flex items-center gap-2">
            <Radio className="w-5 h-5 text-indigo-400 animate-pulse" />
            macOS Audio Voiceover & Real-Time Translation
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            PyAudio Sidecar + Coqui XTTS (Apple Silicon MPS) + Google STT
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`inline-block w-2.5 h-2.5 rounded-full ${
              backendState.is_translating
                ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.7)]"
                : "bg-rose-500"
            }`}
          />
          <span className="text-xs uppercase font-semibold text-slate-400">
            {backendState.is_translating ? "Live" : "Idle"}
          </span>
        </div>
      </header>

      {/* Main Grid */}
      <main className="grid grid-cols-1 md:grid-cols-2 gap-6 flex-1">
        {/* Left Column: Controls & Devices */}
        <section className="space-y-6 bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
          <h2 className="text-sm font-semibold uppercase text-slate-400 tracking-wider">
            Audio Routing & Controls
          </h2>

          {/* Input Device Selection */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
              <Mic className="w-4 h-4 text-indigo-400" />
              Input Device (Microphone / BlackHole Virtual Cable)
            </label>
            <select
              value={selectedInput}
              onChange={(e) => setSelectedInput(Number(e.target.value))}
              disabled={backendState.is_translating}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
            >
              {inputDevices.map((d) => (
                <option key={d.index} value={d.index}>
                  {d.name} (ch: {d.max_input_channels})
                </option>
              ))}
            </select>
          </div>

          {/* Output Device Selection */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
              <Volume2 className="w-4 h-4 text-indigo-400" />
              Output Device (Speakers / Headphones)
            </label>
            <select
              value={selectedOutput}
              onChange={(e) => setSelectedOutput(Number(e.target.value))}
              disabled={backendState.is_translating}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
            >
              {outputDevices.map((d) => (
                <option key={d.index} value={d.index}>
                  {d.name} (ch: {d.max_output_channels})
                </option>
              ))}
            </select>
          </div>

          {/* Ducking Attenuation Slider */}
          <div className="space-y-2 pt-2 border-t border-slate-800">
            <div className="flex justify-between items-center">
              <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
                <VolumeX className="w-4 h-4 text-indigo-400" />
                Sidechain Ducking Level
              </label>
              <span className="text-xs font-mono font-medium text-indigo-400">
                {Math.round(duckingFactor * 100)}%
              </span>
            </div>
            <input
              type="range"
              min="0.0"
              max="1.0"
              step="0.05"
              value={duckingFactor}
              onChange={handleDuckingChange}
              className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
            />
            <p className="text-[11px] text-slate-500">
              Lowers the original audio to this percentage while the translation is speaking.
            </p>
          </div>

          {/* VU Meter & Ducking Indicator */}
          <div className="space-y-2 pt-2 border-t border-slate-800">
            <div className="flex justify-between items-center text-xs">
              <span className="text-slate-400 flex items-center gap-1">
                <Activity className="w-3.5 h-3.5 text-indigo-400" />
                Live Level
              </span>
              <span className="font-mono text-slate-400">
                {backendState.volume_db.toFixed(1)} dB
              </span>
            </div>
            <div className="w-full bg-slate-950 h-2 rounded-full overflow-hidden border border-slate-800">
              <div
                className={`h-full transition-all duration-75 ${
                  backendState.is_ducking ? "bg-amber-500" : "bg-emerald-500"
                }`}
                style={{ width: `${volumePercentage}%` }}
              />
            </div>
            {backendState.is_ducking && (
              <span className="text-[10px] text-amber-400 font-semibold tracking-wider uppercase">
                Ducking Engaged
              </span>
            )}
          </div>

          {/* Action Button */}
          <div className="pt-4">
            <button
              onClick={handleToggleTranslation}
              disabled={isLoading}
              className={`w-full py-3 rounded-lg font-medium text-sm flex items-center justify-center gap-2 transition-all ${
                backendState.is_translating
                  ? "bg-rose-600 hover:bg-rose-500 text-white"
                  : "bg-indigo-600 hover:bg-indigo-500 text-white"
              } disabled:opacity-50`}
            >
              {backendState.is_translating ? (
                <>
                  <Square className="w-4 h-4" /> Stop Translation
                </>
              ) : (
                <>
                  <Play className="w-4 h-4" /> Start Real-Time Translation
                </>
              )}
            </button>
          </div>
        </section>

        {/* Right Column: Live Transcripts */}
        <section className="space-y-4 bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm flex flex-col">
          <h2 className="text-sm font-semibold uppercase text-slate-400 tracking-wider">
            Live Stream Transcripts
          </h2>

          <div className="flex-1 flex flex-col space-y-4">
            {/* Speech-To-Text Output */}
            <div className="flex-1 bg-slate-950 border border-slate-800 rounded-lg p-3 flex flex-col">
              <span className="text-[11px] font-semibold uppercase text-indigo-400 mb-1">
                Source Speech (Original)
              </span>
              <div className="flex-1 overflow-y-auto font-mono text-xs text-slate-300 leading-relaxed">
                {backendState.stt_text || (
                  <span className="text-slate-600 italic">
                    Waiting for incoming voice...
                  </span>
                )}
              </div>
            </div>

            {/* Translation Output */}
            <div className="flex-1 bg-slate-950 border border-slate-800 rounded-lg p-3 flex flex-col">
              <span className="text-[11px] font-semibold uppercase text-emerald-400 mb-1">
                Target Translation & Voiceover
              </span>
              <div className="flex-1 overflow-y-auto font-mono text-xs text-slate-300 leading-relaxed">
                {backendState.translated_text || (
                  <span className="text-slate-600 italic">
                    Translations will appear and speak here...
                  </span>
                )}
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
};
