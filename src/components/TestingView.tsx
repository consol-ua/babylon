import React from "react";
import { AudioDevice, DualBackendState, SampleInfo } from "../api";
import { VuMeter } from "./VuMeter";
import { TranscriptBox } from "./TranscriptBox";
import {
  PlayCircle,
  StopCircle,
  Volume2,
  VolumeX,
  Sparkles,
  CheckCircle2,
  Sliders,
} from "lucide-react";

interface TestingViewProps {
  samples: SampleInfo[];
  selectedSampleId: string;
  onSelectSample: (id: string) => void;
  devices: AudioDevice[];
  headphonesIndex?: number;
  onSelectHeadphones: (index: number) => void;
  partnerLangLabel: string;
  duckingFactor: number;
  onDuckingChange: (factor: number) => void;
  jitterBufferMs: number;
  onJitterBufferChange: (ms: number) => void;
  state: DualBackendState;
  isLoading: boolean;
  onToggleTest: () => void;
}

export const TestingView: React.FC<TestingViewProps> = ({
  samples,
  selectedSampleId,
  onSelectSample,
  devices,
  headphonesIndex,
  onSelectHeadphones,
  partnerLangLabel,
  duckingFactor,
  onDuckingChange,
  jitterBufferMs,
  onJitterBufferChange,
  state,
  isLoading,
  onToggleTest,
}) => {
  const outputDevices = devices.filter((d) => d.max_output_channels > 0);

  return (
    <div className="space-y-6">
      {/* Intro Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
        <div className="flex items-start gap-3.5">
          <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400 mt-0.5">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-slate-100">
              Вбудований тестовий майданчик
            </h2>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed">
              Тестуйте плавну синхронну озвучку з новим Smart DSP Ducking та Jitter Buffer без заїкань і ривків.
            </p>
          </div>
        </div>
      </div>

      {/* Sample Selector Cards */}
      <div className="space-y-3">
        <label className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Оберіть тестовий аудіо-запис
        </label>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {samples.map((sample) => {
            const isSelected = selectedSampleId === sample.id;
            const isPlaying = state.is_testing_active && state.active_sample_id === sample.id;

            return (
              <div
                key={sample.id}
                onClick={() => !state.is_testing_active && onSelectSample(sample.id)}
                className={`p-4 rounded-xl border transition-all cursor-pointer flex flex-col justify-between ${
                  isSelected
                    ? "bg-slate-900 border-indigo-500 ring-1 ring-indigo-500/50 shadow-indigo-500/10 shadow-lg"
                    : "bg-slate-900/60 border-slate-800 hover:border-slate-700 hover:bg-slate-900"
                } ${state.is_testing_active && !isPlaying ? "opacity-50 cursor-not-allowed" : ""}`}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                      {sample.category}
                    </span>
                    {isSelected && (
                      <CheckCircle2 className="w-4 h-4 text-indigo-400" />
                    )}
                  </div>
                  <h3 className="text-sm font-semibold text-slate-200">
                    {sample.title}
                  </h3>
                  <p className="text-xs text-slate-400 mt-1.5 line-clamp-2 leading-relaxed">
                    {sample.description}
                  </p>
                </div>

                {isPlaying && (
                  <div className="mt-3 flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                    Відтворюється та перекладається...
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Audio Output & DSP Controls */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm">
        <div className="space-y-3">
          <div className="space-y-1">
            <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
              <Volume2 className="w-3.5 h-3.5 text-indigo-400" />
              Пристрій виводу (Ваші навушники / динаміки)
            </label>
            <select
              value={headphonesIndex}
              onChange={(e) => onSelectHeadphones(Number(e.target.value))}
              disabled={state.is_testing_active}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
            >
              {outputDevices.map((d) => (
                <option key={d.index} value={d.index}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>

          <VuMeter
            label="Рівень тестового аудіо"
            volumeDb={state.incoming.volume_db}
            isDucking={state.incoming.is_ducking}
            activeColorClass="bg-emerald-500"
          />
        </div>

        <div className="space-y-3">
          {/* Ducking & Jitter Buffer Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1">
              <div className="flex justify-between items-center">
                <label className="text-[11px] font-medium text-slate-300 flex items-center gap-1">
                  <VolumeX className="w-3 h-3 text-emerald-400" />
                  Приглушення (Ducking)
                </label>
                <span className="text-[11px] font-mono font-semibold text-emerald-400">
                  {Math.round(duckingFactor * 100)}%
                </span>
              </div>
              <input
                type="range"
                min="0.0"
                max="1.0"
                step="0.05"
                value={duckingFactor}
                onChange={(e) => onDuckingChange(parseFloat(e.target.value))}
                className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-emerald-500"
              />
            </div>

            <div className="space-y-1">
              <div className="flex justify-between items-center">
                <label className="text-[11px] font-medium text-slate-300 flex items-center gap-1">
                  <Sliders className="w-3 h-3 text-indigo-400" />
                  Згладжування (Jitter)
                </label>
                <span className="text-[11px] font-mono font-semibold text-indigo-400">
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
                className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
              />
            </div>
          </div>

          <div className="pt-2">
            <button
              onClick={onToggleTest}
              disabled={isLoading || state.is_call_active}
              className={`w-full py-2.5 px-4 rounded-lg font-semibold text-xs flex items-center justify-center gap-2 transition-all ${
                state.is_testing_active
                  ? "bg-rose-600 hover:bg-rose-500 text-white"
                  : "bg-emerald-600 hover:bg-emerald-500 text-white"
              } disabled:opacity-50`}
            >
              {state.is_testing_active ? (
                <>
                  <StopCircle className="w-4 h-4" /> Зупинити тест
                </>
              ) : (
                <>
                  <PlayCircle className="w-4 h-4" /> Запустити тест обраного запису
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Live Test Transcripts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <TranscriptBox
          title={`Оригінал із аудіозапису (${partnerLangLabel})`}
          text={state.incoming.stt_text}
          placeholder="Текст із тестового аудіозапису з'явиться тут..."
          themeColor="amber"
        />
        <TranscriptBox
          title="Синхронний переклад (Українська)"
          text={state.incoming.translated_text}
          placeholder="Синхронний український переклад та голос лунатимуть у навушниках..."
          themeColor="emerald"
        />
      </div>
    </div>
  );
};
