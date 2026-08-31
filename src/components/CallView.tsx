import React from "react";
import { AudioDevice, DualBackendState } from "../api";
import { VuMeter } from "./VuMeter";
import { TranscriptBox } from "./TranscriptBox";
import { Mic, Volume2, VolumeX, Play, Square, ArrowRight, PhoneForwarded } from "lucide-react";

interface CallViewProps {
  devices: AudioDevice[];
  myMicIndex?: number;
  onSelectMyMic: (index: number) => void;
  callVirtualMicIndex?: number;
  onSelectCallVirtualMic: (index: number) => void;
  callInputIndex?: number;
  onSelectCallInput: (index: number) => void;
  headphonesIndex?: number;
  onSelectHeadphones: (index: number) => void;
  partnerLangLabel: string;
  duckingFactor: number;
  onDuckingChange: (factor: number) => void;
  state: DualBackendState;
  isLoading: boolean;
  onToggleCall: () => void;
}

export const CallView: React.FC<CallViewProps> = ({
  devices,
  myMicIndex,
  onSelectMyMic,
  callVirtualMicIndex,
  onSelectCallVirtualMic,
  callInputIndex,
  onSelectCallInput,
  headphonesIndex,
  onSelectHeadphones,
  partnerLangLabel,
  duckingFactor,
  onDuckingChange,
  state,
  isLoading,
  onToggleCall,
}) => {
  const inputDevices = devices.filter((d) => d.max_input_channels > 0);
  const outputDevices = devices.filter((d) => d.max_output_channels > 0);

  return (
    <div className="space-y-6">
      {/* 2 Duplex Channels Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Channel 1: Outgoing (Me -> Zoom/Meet) */}
        <section className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4 flex flex-col">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <span className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400">
                <Mic className="w-4 h-4" />
              </span>
              <div>
                <h2 className="text-sm font-semibold text-slate-200">
                  Мій голос для дзвінка
                </h2>
                <p className="text-[11px] text-slate-400">
                  Українська (UA) <ArrowRight className="inline w-3 h-3 mx-0.5" /> {partnerLangLabel}
                </p>
              </div>
            </div>
            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-indigo-900/40 text-indigo-300 border border-indigo-700/50">
              Вихідна лінія
            </span>
          </div>

          {/* Device Controls */}
          <div className="space-y-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
                <Mic className="w-3.5 h-3.5 text-indigo-400" />
                Мій мікрофон (джерело голосу)
              </label>
              <select
                value={myMicIndex}
                onChange={(e) => onSelectMyMic(Number(e.target.value))}
                disabled={state.is_call_active}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
              >
                {inputDevices.map((d) => (
                  <option key={d.index} value={d.index}>
                    {d.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
                <PhoneForwarded className="w-3.5 h-3.5 text-indigo-400" />
                Віртуальний мікрофон для Zoom/Meet (BlackHole)
              </label>
              <select
                value={callVirtualMicIndex}
                onChange={(e) => onSelectCallVirtualMic(Number(e.target.value))}
                disabled={state.is_call_active}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
              >
                <option value="">-- Без виходу (лише транскрипт) --</option>
                {outputDevices.map((d) => (
                  <option key={d.index} value={d.index}>
                    {d.name}
                  </option>
                ))}
              </select>
              <p className="text-[10px] text-slate-500 italic">
                * У Zoom або Meet виберіть цей віртуальний пристрій як свій мікрофон.
              </p>
            </div>

            <VuMeter
              label="Рівень мого мікрофона"
              volumeDb={state.outgoing.volume_db}
              activeColorClass="bg-indigo-500"
            />
          </div>

          {/* Transcripts */}
          <div className="space-y-2.5 flex-1 flex flex-col pt-2 border-t border-slate-800/80">
            <TranscriptBox
              title="Що я сказав (Українська)"
              text={state.outgoing.stt_text}
              placeholder="Говоріть у мікрофон українською..."
              themeColor="indigo"
            />
            <TranscriptBox
              title={`Переклад у Zoom (${partnerLangLabel})`}
              text={state.outgoing.translated_text}
              placeholder="Синхронний AI-переклад транслюватиметься сюди..."
              themeColor="sky"
            />
          </div>
        </section>

        {/* Channel 2: Incoming (Zoom/Meet -> Headphones) */}
        <section className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-4 flex flex-col">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <span className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400">
                <Volume2 className="w-4 h-4" />
              </span>
              <div>
                <h2 className="text-sm font-semibold text-slate-200">
                  Звук співрозмовника
                </h2>
                <p className="text-[11px] text-slate-400">
                  {partnerLangLabel} <ArrowRight className="inline w-3 h-3 mx-0.5" /> Українська (UA)
                </p>
              </div>
            </div>
            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-emerald-900/40 text-emerald-300 border border-emerald-700/50">
              Вхідна лінія
            </span>
          </div>

          {/* Device Controls */}
          <div className="space-y-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
                <Mic className="w-3.5 h-3.5 text-emerald-400" />
                Вхід звуку із Zoom/Meet (BlackHole)
              </label>
              <select
                value={callInputIndex}
                onChange={(e) => onSelectCallInput(Number(e.target.value))}
                disabled={state.is_call_active}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 disabled:opacity-50"
              >
                {inputDevices.map((d) => (
                  <option key={d.index} value={d.index}>
                    {d.name}
                  </option>
                ))}
              </select>
              <p className="text-[10px] text-slate-500 italic">
                * У Zoom або Meet виведіть звук співрозмовника на цей віртуальний аудіокабель.
              </p>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
                <Volume2 className="w-3.5 h-3.5 text-emerald-400" />
                Мої навушники / динаміки (вихід перекладу)
              </label>
              <select
                value={headphonesIndex}
                onChange={(e) => onSelectHeadphones(Number(e.target.value))}
                disabled={state.is_call_active}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 disabled:opacity-50"
              >
                {outputDevices.map((d) => (
                  <option key={d.index} value={d.index}>
                    {d.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Ducking Slider */}
            <div className="space-y-1.5 pt-1">
              <div className="flex justify-between items-center">
                <label className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
                  <VolumeX className="w-3.5 h-3.5 text-emerald-400" />
                  Приглушення оригінального голосу (Ducking)
                </label>
                <span className="text-xs font-mono font-semibold text-emerald-400">
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

            <VuMeter
              label="Рівень звуку дзвінка"
              volumeDb={state.incoming.volume_db}
              isDucking={state.incoming.is_ducking}
              activeColorClass="bg-emerald-500"
            />
          </div>

          {/* Transcripts */}
          <div className="space-y-2.5 flex-1 flex flex-col pt-2 border-t border-slate-800/80">
            <TranscriptBox
              title={`Що каже співрозмовник (${partnerLangLabel})`}
              text={state.incoming.stt_text}
              placeholder="Очікування звуку зі співрозмовника..."
              themeColor="amber"
            />
            <TranscriptBox
              title="Переклад у навушниках (Українська)"
              text={state.incoming.translated_text}
              placeholder="Український голос та переклад з'являться тут..."
              themeColor="emerald"
            />
          </div>
        </section>
      </div>

      {/* Main Action Button */}
      <div className="flex justify-center pt-2">
        <button
          onClick={onToggleCall}
          disabled={isLoading || state.is_testing_active}
          className={`w-full max-w-md py-3.5 px-6 rounded-xl font-semibold text-sm flex items-center justify-center gap-2.5 shadow-lg transition-all ${
            state.is_call_active
              ? "bg-rose-600 hover:bg-rose-500 text-white shadow-rose-900/40"
              : "bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-900/40"
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {state.is_call_active ? (
            <>
              <Square className="w-5 h-5" /> Зупинити синхронний дзвінок
            </>
          ) : (
            <>
              <Play className="w-5 h-5" /> Запустити синхронний переклад дзвінка (Full Duplex)
            </>
          )}
        </button>
      </div>
    </div>
  );
};
