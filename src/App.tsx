import React, { useEffect, useState, useCallback, useMemo } from "react";
import {
  fetchAudioDevices,
  fetchSamples,
  startCall,
  stopCall,
  startSampleTest,
  stopSampleTest,
  updateDuckingFactor,
  updateJitterBuffer,
  subscribeToState,
  AudioDevice,
  SampleInfo,
  DualBackendState,
} from "./api";
import { CallView } from "./components/CallView";
import { TestingView } from "./components/TestingView";
import { LogConsole } from "./components/LogConsole";
import {
  Radio,
  PhoneCall,
  FlaskConical,
  Globe,
  Key,
  Eye,
  EyeOff,
} from "lucide-react";

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

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"call" | "testing">("call");
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [samples, setSamples] = useState<SampleInfo[]>([]);
  const [selectedSampleId, setSelectedSampleId] = useState<string>("it_standup");

  // Language & API Key
  const [partnerLang, setPartnerLang] = useState<string>("en");
  const [apiKey, setApiKey] = useState<string>(() => localStorage.getItem("GEMINI_API_KEY") || "");
  const [showApiKey, setShowApiKey] = useState<boolean>(false);

  // Audio Device Routing
  const [myMicIndex, setMyMicIndex] = useState<number | undefined>();
  const [callVirtualMicIndex, setCallVirtualMicIndex] = useState<number | undefined>();
  const [callInputIndex, setCallInputIndex] = useState<number | undefined>();
  const [headphonesIndex, setHeadphonesIndex] = useState<number | undefined>();

  // DSP & Buffering
  const [duckingFactor, setDuckingFactor] = useState<number>(0.2);
  const [jitterBufferMs, setJitterBufferMs] = useState<number>(150);

  // Backend Live State
  const [backendState, setBackendState] = useState<DualBackendState>({
    is_call_active: false,
    is_testing_active: false,
    active_sample_id: null,
    partner_lang: "en",
    jitter_buffer_ms: 150,
    last_error: null,
    logs: [],
    outgoing: { stt_text: "", translated_text: "", volume_db: -100 },
    incoming: { stt_text: "", translated_text: "", volume_db: -100, is_ducking: false },
  });

  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Initialize Devices and Samples
  useEffect(() => {
    Promise.all([fetchAudioDevices(), fetchSamples()]).then(([devs, smps]) => {
      setDevices(devs);
      setSamples(smps);

      const inputs = devs.filter((d) => d.max_input_channels > 0);
      const outputs = devs.filter((d) => d.max_output_channels > 0);

      // Heuristic for default device selection
      const blackholeIn = inputs.find((d) => d.name.toLowerCase().includes("blackhole"));
      const blackholeOut = outputs.find((d) => d.name.toLowerCase().includes("blackhole"));
      const defaultMic = inputs.find((d) => !d.name.toLowerCase().includes("blackhole")) || inputs[0];
      const defaultHeadphones = outputs.find((d) => !d.name.toLowerCase().includes("blackhole")) || outputs[0];

      if (defaultMic) setMyMicIndex(defaultMic.index);
      if (blackholeOut) setCallVirtualMicIndex(blackholeOut.index);
      if (blackholeIn) setCallInputIndex(blackholeIn.index);
      else if (inputs.length > 1) setCallInputIndex(inputs[1].index);
      if (defaultHeadphones) setHeadphonesIndex(defaultHeadphones.index);
    });

    const unsubscribe = subscribeToState((newState) => {
      setBackendState(newState);
      if (newState.jitter_buffer_ms && newState.jitter_buffer_ms !== jitterBufferMs) {
        setJitterBufferMs(newState.jitter_buffer_ms);
      }
    });

    return () => {
      unsubscribe();
    };
  }, []);

  const handleApiKeyChange = (val: string) => {
    setApiKey(val);
    localStorage.setItem("GEMINI_API_KEY", val);
  };

  const handleDuckingChange = useCallback(async (val: number) => {
    setDuckingFactor(val);
    await updateDuckingFactor(val);
  }, []);

  const handleJitterBufferChange = useCallback(async (val: number) => {
    setJitterBufferMs(val);
    await updateJitterBuffer(val);
  }, []);

  const handleToggleCall = useCallback(async () => {
    setIsLoading(true);
    try {
      if (backendState.is_call_active) {
        await stopCall();
      } else {
        await startCall({
          my_mic_index: myMicIndex,
          call_virtual_mic_index: callVirtualMicIndex,
          call_input_index: callInputIndex,
          headphones_index: headphonesIndex,
          partner_lang: partnerLang,
          ducking_factor: duckingFactor,
          jitter_buffer_ms: jitterBufferMs,
          api_key: apiKey || undefined,
        });
      }
    } catch (err) {
      console.error("[Call Toggle Error]", err);
    } finally {
      setIsLoading(false);
    }
  }, [
    backendState.is_call_active,
    myMicIndex,
    callVirtualMicIndex,
    callInputIndex,
    headphonesIndex,
    partnerLang,
    duckingFactor,
    jitterBufferMs,
    apiKey,
  ]);

  const handleToggleTest = useCallback(async () => {
    setIsLoading(true);
    try {
      if (backendState.is_testing_active) {
        await stopSampleTest();
      } else {
        await startSampleTest({
          sample_id: selectedSampleId,
          headphones_index: headphonesIndex,
          partner_lang: partnerLang,
          ducking_factor: duckingFactor,
          jitter_buffer_ms: jitterBufferMs,
          api_key: apiKey || undefined,
        });
      }
    } catch (err) {
      console.error("[Sample Toggle Error]", err);
    } finally {
      setIsLoading(false);
    }
  }, [
    backendState.is_testing_active,
    selectedSampleId,
    headphonesIndex,
    partnerLang,
    duckingFactor,
    jitterBufferMs,
    apiKey,
  ]);

  const partnerLangOption = useMemo(
    () => SUPPORTED_LANGUAGES.find((l) => l.code === partnerLang) || SUPPORTED_LANGUAGES[0],
    [partnerLang]
  );

  return (
    <div className="flex flex-col min-h-screen bg-slate-950 text-slate-100 p-6 space-y-6">
      {/* Global Header */}
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-wide flex items-center gap-2.5">
            <Radio className="w-5 h-5 text-indigo-400 animate-pulse" />
            Gemini Live Duo Translator
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Двосторонній синхронний AI-перекладач для Zoom та Google Meet (gemini-3.5-live-translate)
          </p>
        </div>

        {/* Global Status Indicators */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg">
            <span
              className={`inline-block w-2.5 h-2.5 rounded-full ${
                backendState.is_call_active
                  ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]"
                  : backendState.is_testing_active
                  ? "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.8)]"
                  : "bg-slate-600"
              }`}
            />
            <span className="text-xs font-semibold text-slate-300">
              {backendState.is_call_active
                ? "Дзвінок активний"
                : backendState.is_testing_active
                ? "Тестування запису"
                : "В очікуванні"}
            </span>
          </div>
        </div>
      </header>

      {/* Shared Configuration Bar: Partner Language & API Key */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-slate-900/80 border border-slate-800/80 rounded-xl p-4">
        {/* Partner Language Selection */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
            <Globe className="w-4 h-4 text-indigo-400" />
            Мова співрозмовника (Ваша мова завжди Українська 🇺🇦)
          </label>
          <select
            value={partnerLang}
            onChange={(e) => setPartnerLang(e.target.value)}
            disabled={backendState.is_call_active || backendState.is_testing_active}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 disabled:opacity-50 font-medium"
          >
            {SUPPORTED_LANGUAGES.map((lang) => (
              <option key={lang.code} value={lang.code}>
                {lang.label}
              </option>
            ))}
          </select>
        </div>

        {/* Gemini API Key */}
        <div className="space-y-1.5">
          <label className="text-xs font-semibold text-slate-300 flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <Key className="w-4 h-4 text-indigo-400" />
              Gemini API Key
            </span>
            <button
              type="button"
              onClick={() => setShowApiKey(!showApiKey)}
              className="text-[11px] text-slate-400 hover:text-slate-200 flex items-center gap-1"
            >
              {showApiKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
              {showApiKey ? "Сховати" : "Показати"}
            </button>
          </label>
          <input
            type={showApiKey ? "text" : "password"}
            placeholder="Введіть AIzaSy... (або залиште порожнім, якщо є .env)"
            value={apiKey}
            onChange={(e) => handleApiKeyChange(e.target.value)}
            disabled={backendState.is_call_active || backendState.is_testing_active}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 disabled:opacity-50 font-mono"
          />
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex border-b border-slate-800 gap-2">
        <button
          onClick={() => setActiveTab("call")}
          className={`flex items-center gap-2 px-5 py-2.5 text-xs font-semibold rounded-t-lg transition-all ${
            activeTab === "call"
              ? "bg-slate-900 text-indigo-400 border-t border-l border-r border-slate-800"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/40"
          }`}
        >
          <PhoneCall className="w-4 h-4" />
          Синхронний дзвінок (Live Call)
        </button>

        <button
          onClick={() => setActiveTab("testing")}
          className={`flex items-center gap-2 px-5 py-2.5 text-xs font-semibold rounded-t-lg transition-all ${
            activeTab === "testing"
              ? "bg-slate-900 text-indigo-400 border-t border-l border-r border-slate-800"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/40"
          }`}
        >
          <FlaskConical className="w-4 h-4" />
          Тестування записів (Demo Playground)
        </button>
      </div>

      {/* Main Tab Content */}
      <main className="space-y-6">
        {activeTab === "call" ? (
          <CallView
            devices={devices}
            myMicIndex={myMicIndex}
            onSelectMyMic={setMyMicIndex}
            callVirtualMicIndex={callVirtualMicIndex}
            onSelectCallVirtualMic={setCallVirtualMicIndex}
            callInputIndex={callInputIndex}
            onSelectCallInput={setCallInputIndex}
            headphonesIndex={headphonesIndex}
            onSelectHeadphones={setHeadphonesIndex}
            partnerLangLabel={partnerLangOption.label}
            duckingFactor={duckingFactor}
            onDuckingChange={handleDuckingChange}
            jitterBufferMs={jitterBufferMs}
            onJitterBufferChange={handleJitterBufferChange}
            state={backendState}
            isLoading={isLoading}
            onToggleCall={handleToggleCall}
          />
        ) : (
          <TestingView
            samples={samples}
            selectedSampleId={selectedSampleId}
            onSelectSample={setSelectedSampleId}
            devices={devices}
            headphonesIndex={headphonesIndex}
            onSelectHeadphones={setHeadphonesIndex}
            partnerLangLabel={partnerLangOption.label}
            duckingFactor={duckingFactor}
            onDuckingChange={handleDuckingChange}
            jitterBufferMs={jitterBufferMs}
            onJitterBufferChange={handleJitterBufferChange}
            state={backendState}
            isLoading={isLoading}
            onToggleTest={handleToggleTest}
          />
        )}

        {/* Global Log & Diagnostic Console */}
        <LogConsole
          logs={backendState.logs}
          lastError={backendState.last_error}
        />
      </main>
    </div>
  );
};
export default App;
