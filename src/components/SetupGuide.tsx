import React, { useState, useEffect } from "react";
import {
  HelpCircle,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  Headphones,
  Mic,
  ArrowRight,
  Layers,
  AlertTriangle,
} from "lucide-react";

type SupportedApp = "zoom" | "meet" | "teams" | "discord";

interface AppGuideInfo {
  name: string;
  micSetting: string;
  speakerSetting: string;
  note?: string;
}

const APP_GUIDES: Record<SupportedApp, AppGuideInfo> = {
  zoom: {
    name: "Zoom",
    micSetting: "BlackHole 2ch",
    speakerSetting: "BlackHole 16ch (або Multi-Output)",
    note: "Вимкніть «Automatically adjust microphone volume» у налаштуваннях Zoom Audio для стабільного рівня звуку.",
  },
  meet: {
    name: "Google Meet",
    micSetting: "BlackHole 2ch",
    speakerSetting: "BlackHole 16ch",
    note: "У вікні дзвінка перейдіть у Налаштування ⚙️ -> Аудіо та оберіть відповідні пристрої.",
  },
  teams: {
    name: "Microsoft Teams",
    micSetting: "BlackHole 2ch",
    speakerSetting: "BlackHole 16ch",
    note: "У розділі Device Settings перевірте, що рівень гучності мікрофона стоїть на 100%.",
  },
  discord: {
    name: "Discord",
    micSetting: "BlackHole 2ch",
    speakerSetting: "BlackHole 16ch",
    note: "Вимкніть «Noise Suppression (Krisp)» та «Echo Cancellation» у Voice & Video, щоб не обрізати синтезований голос.",
  },
};

const STORAGE_KEY = "LIVE_CALL_SETUP_GUIDE_OPEN";
const INSTALL_COMMAND = "brew install blackhole-2ch blackhole-16ch";

export const SetupGuide: React.FC = () => {
  const [isOpen, setIsOpen] = useState<boolean>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved !== null ? saved === "true" : true;
  });

  const [activeApp, setActiveApp] = useState<SupportedApp>("zoom");
  const [isCopied, setIsCopied] = useState<boolean>(false);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, String(isOpen));
  }, [isOpen]);

  const handleCopyCommand = async () => {
    try {
      await navigator.clipboard.writeText(INSTALL_COMMAND);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy command", err);
    }
  };

  const appInfo = APP_GUIDES[activeApp];

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl overflow-hidden shadow-sm transition-all">
      {/* Header / Toggle Button */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-5 py-3.5 flex items-center justify-between bg-slate-900 hover:bg-slate-850 text-left transition-colors border-b border-slate-800/60"
      >
        <div className="flex items-center gap-2.5">
          <span className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400">
            <HelpCircle className="w-4 h-4" />
          </span>
          <div>
            <h3 className="text-xs font-semibold text-slate-200 flex items-center gap-2">
              Як правильно налаштувати аудіо для дзвінка (Zoom / Meet)
              <span className="text-[10px] font-normal text-indigo-400 bg-indigo-950/80 px-2 py-0.5 rounded border border-indigo-800/40">
                Запобігання відлунню
              </span>
            </h3>
            <p className="text-[11px] text-slate-400">
              Покрокова інструкція правильного підключення двох віртуальних кабелів BlackHole
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 text-slate-400 text-xs font-medium">
          <span>{isOpen ? "Згорнути" : "Розгорнути"}</span>
          {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </button>

      {/* Accordion Body */}
      {isOpen && (
        <div className="p-5 space-y-5 text-xs text-slate-300">
          {/* Key Rule Callout */}
          <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-start gap-2.5 text-amber-200/90">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="font-semibold block text-amber-300">
                Чому не можна використовувати один і той самий BlackHole 2ch для входу і виходу?
              </span>
              <p className="text-[11px] leading-relaxed text-amber-200/80">
                Віртуальний кабель BlackHole передає все, що в нього надходить, прямо на свій вхід. Якщо обрати 
                його і для виходу ШІ-перекладу в Zoom, і для входу звуку із Zoom — ваш власний переклад буде 
                закільцьовуватися назад у додаток і звучати у ваших навушниках. 
                <strong> Потрібно використовувати 2 окремі пристрої: 2ch та 16ch!</strong>
              </p>
            </div>
          </div>

          {/* Visual Routing Scheme */}
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-slate-200 font-semibold">
              <Layers className="w-3.5 h-3.5 text-indigo-400" />
              <span>Візуальна схема маршрутизації (2 окремі віртуальні канали)</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* Outgoing Flow Box */}
              <div className="p-3 rounded-lg bg-slate-950 border border-indigo-900/40 space-y-2">
                <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
                  <span className="text-[11px] font-semibold text-indigo-400 flex items-center gap-1">
                    <Mic className="w-3 h-3" /> Лінія 1: Мій голос (Вихід)
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono">UA ➔ Співрозмовник</span>
                </div>
                <div className="space-y-1.5 text-[11px]">
                  <div className="flex items-center gap-1.5 text-slate-300">
                    <span className="font-medium text-slate-400">1.</span>
                    <span>Фізичний мікрофон (MacBook / гарнітура)</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-indigo-300 pl-3">
                    <ArrowRight className="w-3 h-3 text-indigo-400 shrink-0" />
                    <span>Gemini Live перекладає на іноземну мову</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-slate-300 pl-3">
                    <ArrowRight className="w-3 h-3 text-indigo-400 shrink-0" />
                    <span>Вихід у <strong className="text-indigo-300">BlackHole 2ch</strong></span>
                  </div>
                  <div className="flex items-center gap-1.5 text-emerald-400 pl-3 font-semibold">
                    <ArrowRight className="w-3 h-3 text-indigo-400 shrink-0" />
                    <span>У Zoom обираємо: Мікрофон = BlackHole 2ch</span>
                  </div>
                </div>
              </div>

              {/* Incoming Flow Box */}
              <div className="p-3 rounded-lg bg-slate-950 border border-emerald-900/40 space-y-2">
                <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
                  <span className="text-[11px] font-semibold text-emerald-400 flex items-center gap-1">
                    <Headphones className="w-3 h-3" /> Лінія 2: Звук співрозмовника (Вхід)
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono">Співрозмовник ➔ UA</span>
                </div>
                <div className="space-y-1.5 text-[11px]">
                  <div className="flex items-center gap-1.5 text-emerald-400 font-semibold">
                    <span className="font-medium text-slate-400">1.</span>
                    <span>У Zoom обираємо: Динамік = BlackHole 16ch</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-slate-300 pl-3">
                    <ArrowRight className="w-3 h-3 text-emerald-400 shrink-0" />
                    <span>Додаток захоплює з <strong className="text-emerald-300">BlackHole 16ch</strong></span>
                  </div>
                  <div className="flex items-center gap-1.5 text-emerald-300 pl-3">
                    <ArrowRight className="w-3 h-3 text-emerald-400 shrink-0" />
                    <span>Gemini Live озвучує українською</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-slate-300 pl-3">
                    <ArrowRight className="w-3 h-3 text-emerald-400 shrink-0" />
                    <span>Слухаємо у <strong className="text-indigo-300">Фізичних навушниках</strong></span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* 3 Step Setup Guide */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-1">
            {/* Step 1: Install */}
            <div className="bg-slate-950 p-3.5 rounded-lg border border-slate-800 space-y-2.5 flex flex-col justify-between">
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="w-5 h-5 rounded-full bg-indigo-600 text-white font-bold text-[10px] flex items-center justify-center">
                    1
                  </span>
                  <h4 className="font-semibold text-slate-200">Встановлення драйверів</h4>
                </div>
                <p className="text-[11px] text-slate-400 leading-snug">
                  Для розділення потоків встановіть обидва віртуальні аудіодрайвери через Homebrew:
                </p>
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-700/80 rounded-md p-1.5">
                  <code className="text-[10px] font-mono text-indigo-300 select-all truncate flex-1">
                    {INSTALL_COMMAND}
                  </code>
                  <button
                    type="button"
                    onClick={handleCopyCommand}
                    title="Скопіювати команду"
                    className="p-1 rounded bg-slate-800 hover:bg-indigo-600 text-slate-300 hover:text-white transition-colors"
                  >
                    {isCopied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  </button>
                </div>
                {isCopied && (
                  <p className="text-[10px] text-emerald-400 text-right">Скопійовано в буфер!</p>
                )}
              </div>
            </div>

            {/* Step 2: In-App Settings */}
            <div className="bg-slate-950 p-3.5 rounded-lg border border-slate-800 space-y-2 flex flex-col justify-between">
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="w-5 h-5 rounded-full bg-indigo-600 text-white font-bold text-[10px] flex items-center justify-center">
                    2
                  </span>
                  <h4 className="font-semibold text-slate-200">Налаштування у додатку</h4>
                </div>
                <ul className="text-[11px] space-y-1.5 text-slate-300">
                  <li className="flex items-start gap-1.5">
                    <span className="text-indigo-400">•</span>
                    <span><strong>Мій мікрофон:</strong> ваш фізичний мікрофон</span>
                  </li>
                  <li className="flex items-start gap-1.5">
                    <span className="text-indigo-400">•</span>
                    <span><strong>Віртуальний мікрофон:</strong> BlackHole 2ch</span>
                  </li>
                  <li className="flex items-start gap-1.5">
                    <span className="text-emerald-400">•</span>
                    <span><strong>Вхід звуку із Zoom:</strong> BlackHole 16ch</span>
                  </li>
                  <li className="flex items-start gap-1.5">
                    <span className="text-emerald-400">•</span>
                    <span><strong>Мої навушники:</strong> ваші фізичні навушники</span>
                  </li>
                </ul>
              </div>
            </div>

            {/* Step 3: Zoom / Meeting App Settings */}
            <div className="bg-slate-950 p-3.5 rounded-lg border border-slate-800 space-y-2 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <span className="w-5 h-5 rounded-full bg-indigo-600 text-white font-bold text-[10px] flex items-center justify-center">
                      3
                    </span>
                    <h4 className="font-semibold text-slate-200">Налаштування у сервісі</h4>
                  </div>
                </div>

                {/* App Switcher Tabs */}
                <div className="flex gap-1 bg-slate-900 p-0.5 rounded border border-slate-800 mb-2">
                  {(["zoom", "meet", "teams", "discord"] as SupportedApp[]).map((appKey) => (
                    <button
                      key={appKey}
                      type="button"
                      onClick={() => setActiveApp(appKey)}
                      className={`flex-1 py-1 text-[10px] font-medium rounded transition-colors capitalize ${
                        activeApp === appKey
                          ? "bg-indigo-600 text-white shadow-sm"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      {appKey === "meet" ? "Meet" : appKey}
                    </button>
                  ))}
                </div>

                <div className="space-y-1.5 text-[11px] text-slate-300">
                  <div>
                    <span className="text-slate-400">Мікрофон ({appInfo.name}):</span>{" "}
                    <strong className="text-indigo-400">{appInfo.micSetting}</strong>
                  </div>
                  <div>
                    <span className="text-slate-400">Динамік ({appInfo.name}):</span>{" "}
                    <strong className="text-emerald-400">{appInfo.speakerSetting}</strong>
                  </div>
                  {appInfo.note && (
                    <p className="text-[10px] text-slate-400 italic pt-1 border-t border-slate-850">
                      💡 {appInfo.note}
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
