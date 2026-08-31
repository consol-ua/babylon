import React, { useState } from "react";
import { AudioDevice, DualBackendState, GeminiVoice } from "../api";
import { VuMeter } from "./VuMeter";
import { TranscriptBox } from "./TranscriptBox";
import {
  Video,
  Volume2,
  VolumeX,
  Play,
  Square,
  ArrowRight,
  Sliders,
  Sparkles,
  HelpCircle,
  ChevronDown,
  ChevronUp,
  Headphones,
  Radio,
  Layers,
  Info,
} from "lucide-react";

interface DubbingViewProps {
  devices: AudioDevice[];
  voices: GeminiVoice[];
  dubbingInputIndex?: number;
  onSelectDubbingInput: (index: number) => void;
  headphonesIndex?: number;
  onSelectHeadphones: (index: number) => void;
  sourceLangLabel: string;
  sourceLangCode: string;
  dubbingVoice: string;
  onSelectDubbingVoice: (voice: string) => void;
  duckingFactor: number;
  onDuckingChange: (factor: number) => void;
  jitterBufferMs: number;
  onJitterBufferChange: (ms: number) => void;
  state: DualBackendState;
  isLoading: boolean;
  onToggleDubbing: () => void;
}

export const DubbingView: React.FC<DubbingViewProps> = ({
  devices,
  voices,
  dubbingInputIndex,
  onSelectDubbingInput,
  headphonesIndex,
  onSelectHeadphones,
  sourceLangLabel,
  sourceLangCode,
  dubbingVoice,
  onSelectDubbingVoice,
  duckingFactor,
  onDuckingChange,
  jitterBufferMs,
  onJitterBufferChange,
  state,
  isLoading,
  onToggleDubbing,
}) => {
  const [showSetupGuide, setShowSetupGuide] = useState<boolean>(false);
  const inputDevices = devices.filter((d) => d.max_input_channels > 0);
  const outputDevices = devices.filter((d) => d.max_output_channels > 0);

  const isDubbing = Boolean(state.is_dubbing_active);
  const isAnyOtherActive =
    state.is_call_active || state.is_testing_active || state.is_mic_test_active;

  return (
    <div className="space-y-6">
      {/* Top Banner / Description */}
      <div className="bg-gradient-to-r from-indigo-950/40 via-slate-900 to-slate-900 border border-indigo-900/40 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="p-2.5 rounded-lg bg-indigo-500/10 text-indigo-400 mt-0.5">
            <Video className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
              Односторонній дубляж медіа та YouTube
              <span className="text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-full">
                Без мікрофона
              </span>
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Захоплює звук відео/стріму з віртуального пристрою (BlackHole), перекладає через Gemini Live та озвучує українською у ваші навушники з автоприглушенням фону.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setShowSetupGuide(!showSetupGuide)}
          className="self-start md:self-center flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-800 text-slate-300 text-xs font-medium border border-slate-700 transition"
        >
          <HelpCircle className="w-3.5 h-3.5 text-indigo-400" />
          <span>Як налаштувати звук у macOS</span>
          {showSetupGuide ? (
            <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
          )}
        </button>
      </div>

      {/* Collapsible macOS Audio Routing Helper */}
      {showSetupGuide && (
        <div className="bg-slate-900 border border-indigo-500/30 rounded-xl p-4 text-xs text-slate-300 space-y-3">
          <div className="flex items-center gap-2 font-semibold text-indigo-300">
            <Info className="w-4 h-4 text-indigo-400" />
            Інструкція з роутингу аудіо з YouTube / Браузера:
          </div>
          <ol className="list-decimal list-inside space-y-1.5 text-slate-300 pl-1">
            <li>
              Переконайтеся, що встановлено віртуальний аудіокабель (наприклад, <span className="font-mono text-indigo-300">BlackHole 2ch</span> або <span className="font-mono text-indigo-300">Loopback</span>).
            </li>
            <li>
              <strong>Варіант А (Простий):</strong> У налаштуваннях звуку macOS або в браузері виберіть виходом <span className="font-semibold text-slate-100">BlackHole 2ch</span>. У додатку нижче виберіть <span className="font-semibold text-slate-100">Вхід: BlackHole</span> та <span className="font-semibold text-slate-100">Вихід: Ваші навушники</span>.
            </li>
            <li>
              <strong>Варіант Б (Multi-Output):</strong> Утиліта <em>Audio MIDI Setup</em> $\rightarrow$ створіть «Multi-Output Device», увімкніть одночасно навушники та BlackHole, і виберіть його системним виходом macOS.
            </li>
            <li>
              Увімкніть відео на YouTube та натисніть зелену кнопку <strong>«Почати дублювання»</strong>.
            </li>
          </ol>
        </div>
      )}

      {/* Routing & Voice Controls Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Card 1: Input & Output Devices */}
        <section className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <span className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400">
                <Layers className="w-4 h-4" />
              </span>
              <h3 className="text-sm font-semibold text-slate-200">
                Аудіопристрої
              </h3>
            </div>
            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
              Роутинг
            </span>
          </div>

          <div className="space-y-4">
            {/* Input Device (e.g. BlackHole) */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300 flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <Radio className="w-3.5 h-3.5 text-indigo-400" />
                  Джерело звуку відео (Віртуальний вхід)
                </span>
                <span className="text-[11px] text-slate-400">BlackHole / Вхід</span>
              </label>
              <select
                value={dubbingInputIndex ?? ""}
                onChange={(e) => onSelectDubbingInput(Number(e.target.value))}
                disabled={isDubbing || isAnyOtherActive}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
              >
                {inputDevices.map((d) => (
                  <option key={d.index} value={d.index}>
                    {d.name} {d.name.toLowerCase().includes("blackhole") ? "★ (Рекомендовано)" : ""}
                  </option>
                ))}
              </select>
            </div>

            {/* Output Device (Headphones) */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300 flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <Headphones className="w-3.5 h-3.5 text-indigo-400" />
                  Вихідний пристрій (Навушники / Динаміки)
                </span>
                <span className="text-[11px] text-slate-400">Куди чути дубляж</span>
              </label>
              <select
                value={headphonesIndex ?? ""}
                onChange={(e) => onSelectHeadphones(Number(e.target.value))}
                disabled={isDubbing || isAnyOtherActive}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
              >
                {outputDevices.map((d) => (
                  <option key={d.index} value={d.index}>
                    {d.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </section>

        {/* Card 2: Voice & Direction */}
        <section className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <span className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400">
                <Sparkles className="w-4 h-4" />
              </span>
              <h3 className="text-sm font-semibold text-slate-200">
                Мова та голос перекладу
              </h3>
            </div>
            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-700/50">
              AI Модель
            </span>
          </div>

          <div className="space-y-4">
            {/* Translation Flow Badge */}
            <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between text-xs">
              <div className="text-slate-400">Напрямок дубляжу:</div>
              <div className="font-semibold text-slate-200 flex items-center gap-1.5">
                <span>{sourceLangLabel.split(" ")[0]} ({sourceLangCode.toUpperCase()})</span>
                <ArrowRight className="w-3.5 h-3.5 text-indigo-400" />
                <span className="text-indigo-300">Українська 🇺🇦 (UK)</span>
              </div>
            </div>

            {/* Dubbing Voice Selection */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-300 flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                  Голос українського дубляжу (Gemini Live)
                </span>
              </label>
              <select
                value={dubbingVoice}
                onChange={(e) => onSelectDubbingVoice(e.target.value)}
                disabled={isDubbing || isAnyOtherActive}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
              >
                {voices.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </section>
      </div>

      {/* DSP Controls: Smart Ducking & Jitter Buffer */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
          <Sliders className="w-4 h-4 text-indigo-400" />
          <h3 className="text-sm font-semibold text-slate-200">
            Налаштування зведення аудіо та DSP
          </h3>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Smart Ducking Slider */}
          <div className="space-y-2">
            <div className="flex justify-between items-center text-xs">
              <span className="font-medium text-slate-300 flex items-center gap-1.5">
                {duckingFactor === 0 ? (
                  <VolumeX className="w-3.5 h-3.5 text-rose-400" />
                ) : (
                  <Volume2 className="w-3.5 h-3.5 text-indigo-400" />
                )}
                Smart Ducking (Рівень гучності відео під час мовлення ШІ)
              </span>
              <span className="font-mono text-indigo-400 font-semibold bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                {Math.round(duckingFactor * 100)}%
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={duckingFactor}
              onChange={(e) => onDuckingChange(parseFloat(e.target.value))}
              className="w-full h-1.5 bg-slate-950 rounded-lg appearance-none cursor-pointer accent-indigo-500"
            />
            <div className="flex justify-between text-[10px] text-slate-400">
              <span>0% (Повне глушіння відео)</span>
              <span>20% (Рекомендовано)</span>
              <span>100% (Без приглушення)</span>
            </div>
          </div>

          {/* Jitter Buffer Slider */}
          <div className="space-y-2">
            <div className="flex justify-between items-center text-xs">
              <span className="font-medium text-slate-300">
                Jitter Buffer (Буфер плавного відтворення)
              </span>
              <span className="font-mono text-indigo-400 font-semibold bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                {jitterBufferMs} мс
              </span>
            </div>
            <input
              type="range"
              min="50"
              max="400"
              step="25"
              value={jitterBufferMs}
              onChange={(e) => onJitterBufferChange(parseInt(e.target.value, 10))}
              className="w-full h-1.5 bg-slate-950 rounded-lg appearance-none cursor-pointer accent-indigo-500"
            />
            <div className="flex justify-between text-[10px] text-slate-400">
              <span>50 мс (Мінімальна затримка)</span>
              <span>150 мс (Баланс)</span>
              <span>400 мс (Максимальна стабільність)</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Start / Stop Action Banner */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-5 bg-slate-900 border border-slate-800 rounded-xl">
        <div className="flex items-center gap-3">
          <div
            className={`w-3.5 h-3.5 rounded-full ${
              isDubbing
                ? "bg-emerald-500 animate-pulse shadow-[0_0_12px_rgba(16,185,129,0.8)]"
                : "bg-slate-600"
            }`}
          />
          <div>
            <div className="text-sm font-semibold text-slate-100">
              {isDubbing ? "Синхронне дублювання активне" : "Готовий до дублювання відео"}
            </div>
            <div className="text-xs text-slate-400">
              {isDubbing
                ? "Звук відео захоплюється, передається в Gemini Live та транслюється в навушники."
                : "Увімкніть відео в браузері та натисніть кнопку для старту перекладу."}
            </div>
          </div>
        </div>

        <button
          onClick={onToggleDubbing}
          disabled={isLoading || (!isDubbing && isAnyOtherActive)}
          className={`flex items-center justify-center gap-2.5 px-7 py-3 rounded-xl font-semibold text-sm transition-all shadow-lg min-w-[220px] ${
            isDubbing
              ? "bg-rose-600 hover:bg-rose-500 text-white shadow-rose-900/40"
              : "bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-900/40"
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {isDubbing ? (
            <>
              <Square className="w-4 h-4 fill-current" />
              Зупинити дублювання
            </>
          ) : (
            <>
              <Play className="w-4 h-4 fill-current" />
              Почати дублювання
            </>
          )}
        </button>
      </div>

      {/* Live Audio Telemetry VU Meter & Ducking Indicator */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-indigo-400" />
            <h3 className="text-sm font-semibold text-slate-200">
              Рівень аудіопотоку та стан приглушення фону
            </h3>
          </div>
          {state.incoming.is_ducking && (
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/30 animate-pulse">
              Smart Ducking Активно
            </span>
          )}
        </div>

        <div className="space-y-2">
          <VuMeter
            label="Рівень вхідного сигналу відео (BlackHole)"
            volumeDb={state.incoming.volume_db}
            isDucking={state.incoming.is_ducking}
            activeColorClass="bg-indigo-500"
          />
        </div>
      </div>

      {/* Live Transcripts: Original Video Speech & Ukrainian Translation */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <TranscriptBox
          title={`Оригінальна мова відео (${sourceLangLabel.split(" ")[0]})`}
          text={state.incoming.stt_text}
          placeholder="Очікування виявлення мовлення у відеопотоці..."
          themeColor="indigo"
        />

        <TranscriptBox
          title="Український синхронний переклад 🇺🇦"
          text={state.incoming.translated_text}
          placeholder="Переклад з'явиться тут у реальному часі..."
          themeColor="emerald"
        />
      </div>
    </div>
  );
};
