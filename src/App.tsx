import React, { useEffect, useState, useCallback, useMemo } from "react";
import {
  fetchAudioDevices,
  fetchSamples,
  fetchVoices,
  startCall,
  stopCall,
  startDubbing,
  stopDubbing,
  startSampleTest,
  stopSampleTest,
  startMicTest,
  stopMicTest,
  updateDuckingFactor,
  updateJitterBuffer,
  subscribeToState,
  AudioDevice,
  SampleInfo,
  GeminiVoice,
  DualBackendState,
  MicTestResult,
} from "./api";
import { CallView } from "./components/CallView";
import { DubbingView } from "./components/DubbingView";
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
  Video,
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

export const DEFAULT_VOICES: GeminiVoice[] = [
  { id: "Puck", label: "Puck (Чоловічий / Енергійний, природний)", gender: "male" },
  { id: "Charon", label: "Charon (Чоловічий / Впевнений, спокійний)", gender: "male" },
  { id: "Fenrir", label: "Fenrir (Чоловічий / Низький тембр)", gender: "male" },
  { id: "Aoede", label: "Aoede (Жіночий / Виразний, глибокий)", gender: "female" },
  { id: "Kore", label: "Kore (Жіночий / Спокійний, м'який)", gender: "female" },
];

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"call" | "dubbing" | "testing">("call");
  const [devices, setDevices] = useState<AudioDevice[]>([]);
  const [samples, setSamples] = useState<SampleInfo[]>([]);
  const [voices, setVoices] = useState<GeminiVoice[]>(DEFAULT_VOICES);
  const [selectedSampleId, setSelectedSampleId] = useState<string>("it_standup");

  // Language, Voices & API Key
  const [partnerLang, setPartnerLang] = useState<string>("en");
  const [outgoingVoice, setOutgoingVoice] = useState<string>("Puck");
  const [incomingVoice, setIncomingVoice] = useState<string>("Aoede");
  const [dubbingVoice, setDubbingVoice] = useState<string>("Aoede");
  const [sampleVoice, setSampleVoice] = useState<string>("Aoede");
  const [micTestVoice, setMicTestVoice] = useState<string>("Puck");

  const [apiKey, setApiKey] = useState<string>(() => localStorage.getItem("GEMINI_API_KEY") || "");
  const [showApiKey, setShowApiKey] = useState<boolean>(false);

  // Audio Device Routing
  const [myMicIndex, setMyMicIndex] = useState<number | undefined>();
  const [callVirtualMicIndex, setCallVirtualMicIndex] = useState<number | undefined>();
  const [callInputIndex, setCallInputIndex] = useState<number | undefined>();
  const [dubbingInputIndex, setDubbingInputIndex] = useState<number | undefined>();
  const [headphonesIndex, setHeadphonesIndex] = useState<number | undefined>();

  // DSP & Buffering
  const [duckingFactor, setDuckingFactor] = useState<number>(0.2);
  const [jitterBufferMs, setJitterBufferMs] = useState<number>(150);

  // Backend Live State
  const [backendState, setBackendState] = useState<DualBackendState>({
    is_call_active: false,
    is_dubbing_active: false,
    is_testing_active: false,
    is_mic_test_active: false,
    active_sample_id: null,
    partner_lang: "en",
    outgoing_voice: "Puck",
    incoming_voice: "Aoede",
    jitter_buffer_ms: 150,
    mic_test_latency_ms: 0,
    last_error: null,
    logs: [],
    outgoing: { stt_text: "", translated_text: "", volume_db: -100 },
    incoming: { stt_text: "", translated_text: "", volume_db: -100, is_ducking: false },
  });

  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Initialize Devices, Samples, and Voices
  useEffect(() => {
    Promise.all([fetchAudioDevices(), fetchSamples(), fetchVoices()]).then(
      ([devs, smps, vcs]) => {
        setDevices(devs);
        setSamples(smps);
        if (vcs.length > 0) setVoices(vcs);

        const inputs = devs.filter((d) => d.max_input_channels > 0);
        const outputs = devs.filter((d) => d.max_output_channels > 0);

        const blackholeIn = inputs.find((d) => d.name.toLowerCase().includes("blackhole"));
        const blackholeOut = outputs.find((d) => d.name.toLowerCase().includes("blackhole"));
        const defaultMic = inputs.find((d) => !d.name.toLowerCase().includes("blackhole")) || inputs[0];
        const defaultHeadphones = outputs.find((d) => !d.name.toLowerCase().includes("blackhole")) || outputs[0];

        if (defaultMic) setMyMicIndex(defaultMic.index);
        if (blackholeOut) setCallVirtualMicIndex(blackholeOut.index);
        if (blackholeIn) {
          setCallInputIndex(blackholeIn.index);
          setDubbingInputIndex(blackholeIn.index);
        } else if (inputs.length > 1) {
          setCallInputIndex(inputs[1].index);
          setDubbingInputIndex(inputs[1].index);
        } else if (inputs.length > 0) {
          setDubbingInputIndex(inputs[0].index);
        }
        if (defaultHeadphones) setHeadphonesIndex(defaultHeadphones.index);
      }
    );

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
          outgoing_voice: outgoingVoice,
          incoming_voice: incomingVoice,
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
    outgoingVoice,
    incomingVoice,
    duckingFactor,
    jitterBufferMs,
    apiKey,
  ]);

  const handleToggleDubbing = useCallback(async () => {
    setIsLoading(true);
    try {
      if (backendState.is_dubbing_active) {
        await stopDubbing();
      } else {
        await startDubbing({
          input_device_index: dubbingInputIndex,
          headphones_index: headphonesIndex,
          source_lang: partnerLang,
          voice_name: dubbingVoice,
          ducking_factor: duckingFactor,
          jitter_buffer_ms: jitterBufferMs,
          api_key: apiKey || undefined,
        });
      }
    } catch (err) {
      console.error("[Dubbing Toggle Error]", err);
    } finally {
      setIsLoading(false);
    }
  }, [
    backendState.is_dubbing_active,
    dubbingInputIndex,
    headphonesIndex,
    partnerLang,
    dubbingVoice,
    duckingFactor,
    jitterBufferMs,
    apiKey,
  ]);

  const handleToggleSampleTest = useCallback(async () => {
    setIsLoading(true);
    try {
      if (backendState.is_testing_active) {
        await stopSampleTest();
      } else {
        await startSampleTest({
          sample_id: selectedSampleId,
          headphones_index: headphonesIndex,
          partner_lang: partnerLang,
          voice_name: sampleVoice,
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
    sampleVoice,
    duckingFactor,
    jitterBufferMs,
    apiKey,
  ]);

  const handleStartMicTest = useCallback(async () => {
    setIsLoading(true);
    try {
      await startMicTest({
        mic_index: myMicIndex,
        partner_lang: partnerLang,
        voice_name: micTestVoice,
        api_key: apiKey || undefined,
      });
    } catch (err) {
      console.error("[Mic Test Start Error]", err);
    } finally {
      setIsLoading(false);
    }
  }, [myMicIndex, partnerLang, micTestVoice, apiKey]);

  const handleStopMicTest = useCallback(async (): Promise<MicTestResult | undefined> => {
    setIsLoading(true);
    try {
      return await stopMicTest();
    } catch (err) {
      console.error("[Mic Test Stop Error]", err);
      return undefined;
    } finally {
      setIsLoading(false);
    }
  }, []);

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
                backendState.is_call_active || backendState.is_dubbing_active
                  ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]"
                  : backendState.is_testing_active || backendState.is_mic_test_active
                  ? "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.8)]"
                  : "bg-slate-600"
              }`}
            />
            <span className="text-xs font-semibold text-slate-300">
              {backendState.is_call_active
                ? "Дзвінок активний"
                : backendState.is_dubbing_active
                ? "Дублювання відео активне"
                : backendState.is_testing_active
                ? "Тестування запису"
                : backendState.is_mic_test_active
                ? "Запис тесту мікрофона"
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
            Мова співрозмовника / відео (Ваша мова завжди Українська 🇺🇦)
          </label>
          <select
            value={partnerLang}
            onChange={(e) => setPartnerLang(e.target.value)}
            disabled={
              backendState.is_call_active ||
              backendState.is_dubbing_active ||
              backendState.is_testing_active ||
              backendState.is_mic_test_active
            }
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
            disabled={
              backendState.is_call_active ||
              backendState.is_dubbing_active ||
              backendState.is_testing_active ||
              backendState.is_mic_test_active
            }
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
          onClick={() => setActiveTab("dubbing")}
          className={`flex items-center gap-2 px-5 py-2.5 text-xs font-semibold rounded-t-lg transition-all ${
            activeTab === "dubbing"
              ? "bg-slate-900 text-indigo-400 border-t border-l border-r border-slate-800"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/40"
          }`}
        >
          <Video className="w-4 h-4" />
          Дублювання відео (YouTube / Media)
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
          Тестування та мікрофон (Playground)
        </button>
      </div>

      {/* Main Tab Content */}
      <main className="space-y-6">
        {activeTab === "call" ? (
          <CallView
            devices={devices}
            voices={voices}
            myMicIndex={myMicIndex}
            onSelectMyMic={setMyMicIndex}
            callVirtualMicIndex={callVirtualMicIndex}
            onSelectCallVirtualMic={setCallVirtualMicIndex}
            callInputIndex={callInputIndex}
            onSelectCallInput={setCallInputIndex}
            headphonesIndex={headphonesIndex}
            onSelectHeadphones={setHeadphonesIndex}
            partnerLangLabel={partnerLangOption.label}
            outgoingVoice={outgoingVoice}
            onSelectOutgoingVoice={setOutgoingVoice}
            incomingVoice={incomingVoice}
            onSelectIncomingVoice={setIncomingVoice}
            duckingFactor={duckingFactor}
            onDuckingChange={handleDuckingChange}
            jitterBufferMs={jitterBufferMs}
            onJitterBufferChange={handleJitterBufferChange}
            state={backendState}
            isLoading={isLoading}
            onToggleCall={handleToggleCall}
          />
        ) : activeTab === "dubbing" ? (
          <DubbingView
            devices={devices}
            voices={voices}
            dubbingInputIndex={dubbingInputIndex}
            onSelectDubbingInput={setDubbingInputIndex}
            headphonesIndex={headphonesIndex}
            onSelectHeadphones={setHeadphonesIndex}
            sourceLangLabel={partnerLangOption.label}
            sourceLangCode={partnerLangOption.code}
            dubbingVoice={dubbingVoice}
            onSelectDubbingVoice={setDubbingVoice}
            duckingFactor={duckingFactor}
            onDuckingChange={handleDuckingChange}
            jitterBufferMs={jitterBufferMs}
            onJitterBufferChange={handleJitterBufferChange}
            state={backendState}
            isLoading={isLoading}
            onToggleDubbing={handleToggleDubbing}
          />
        ) : (
          <TestingView
            samples={samples}
            voices={voices}
            selectedSampleId={selectedSampleId}
            onSelectSample={setSelectedSampleId}
            devices={devices}
            myMicIndex={myMicIndex}
            onSelectMyMic={setMyMicIndex}
            headphonesIndex={headphonesIndex}
            onSelectHeadphones={setHeadphonesIndex}
            partnerLangLabel={partnerLangOption.label}
            sampleVoice={sampleVoice}
            onSelectSampleVoice={setSampleVoice}
            micTestVoice={micTestVoice}
            onSelectMicTestVoice={setMicTestVoice}
            duckingFactor={duckingFactor}
            onDuckingChange={handleDuckingChange}
            jitterBufferMs={jitterBufferMs}
            onJitterBufferChange={handleJitterBufferChange}
            state={backendState}
            isLoading={isLoading}
            onToggleSampleTest={handleToggleSampleTest}
            onStartMicTest={handleStartMicTest}
            onStopMicTest={handleStopMicTest}
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
