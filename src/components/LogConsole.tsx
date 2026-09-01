import React, { useState, useMemo } from "react";
import { LogEntry } from "../api";
import {
  Terminal,
  AlertTriangle,
  Info,
  XCircle,
  Copy,
  Check,
  Trash2,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

interface LogConsoleProps {
  logs: LogEntry[];
  lastError: string | null;
}

export const LogConsole = React.memo<LogConsoleProps>(({
  logs,
  lastError,
}) => {
  const [isOpen, setIsOpen] = useState<boolean>(true);
  const [filter, setFilter] = useState<"ALL" | "ERROR" | "WARN" | "INFO">("ALL");
  const [copied, setCopied] = useState<boolean>(false);
  const [clearedAt, setClearedAt] = useState<string | null>(null);

  const displayedLogs = useMemo(() => {
    let source = logs;
    if (clearedAt) {
      source = logs.filter(l => l.timestamp > clearedAt);
    }
    if (filter === "ALL") return source;
    return source.filter(l => l.level === filter);
  }, [logs, clearedAt, filter]);

  const handleCopyLogs = async () => {
    const formatted = displayedLogs
      .map((l) => `[${l.timestamp}] [${l.level}] [${l.source}]: ${l.message}`)
      .join("\n");
    if (!formatted) return;
    try {
      await navigator.clipboard.writeText(formatted);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  const handleClear = () => {
    const now = new Date().toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setClearedAt(now);
  };

  const errorCount = useMemo(
    () => logs.filter((l) => l.level === "ERROR").length,
    [logs]
  );

  return (
    <div className="space-y-3">
      {/* Critical Error Alert Banner */}
      {lastError && (
        <div className="bg-rose-950/80 border border-rose-700/60 rounded-xl p-4 flex items-start gap-3 shadow-lg shadow-rose-950/40 animate-pulse">
          <XCircle className="w-5 h-5 text-rose-400 mt-0.5 shrink-0" />
          <div className="space-y-1">
            <h4 className="text-xs font-bold uppercase tracking-wider text-rose-300">
              Помилка Gemini API / Аудіо
            </h4>
            <p className="text-xs text-rose-200 leading-relaxed font-mono">
              {lastError}
            </p>
          </div>
        </div>
      )}

      {/* Main Console Box */}
      <div className="bg-slate-900/95 border border-slate-800 rounded-xl overflow-hidden shadow-sm">
        {/* Header Bar */}
        <div className="flex items-center justify-between px-4 py-2.5 bg-slate-950/80 border-b border-slate-800">
          <div className="flex items-center gap-2.5">
            <Terminal className="w-4 h-4 text-indigo-400" />
            <span className="text-xs font-semibold text-slate-300">
              Журнал подій та помилок (Log Console)
            </span>
            {errorCount > 0 && (
              <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30">
                {errorCount} помилок
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Filter buttons */}
            <div className="flex items-center bg-slate-900 rounded-lg p-0.5 border border-slate-800 text-[10px] font-semibold">
              {(["ALL", "ERROR", "WARN", "INFO"] as const).map((lvl) => (
                <button
                  key={lvl}
                  onClick={() => setFilter(lvl)}
                  className={`px-2 py-0.5 rounded transition-all ${
                    filter === lvl
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {lvl === "ALL" ? "Всі" : lvl}
                </button>
              ))}
            </div>

            <button
              onClick={handleCopyLogs}
              title="Скопіювати всі логи"
              className="text-slate-400 hover:text-slate-200 p-1 rounded hover:bg-slate-800 transition-colors"
            >
              {copied ? (
                <Check className="w-3.5 h-3.5 text-emerald-400" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
            </button>

            <button
              onClick={handleClear}
              title="Очистити вивід"
              className="text-slate-400 hover:text-slate-200 p-1 rounded hover:bg-slate-800 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>

            <button
              onClick={() => setIsOpen(!isOpen)}
              className="text-slate-400 hover:text-slate-200 p-1 rounded hover:bg-slate-800 transition-colors"
            >
              {isOpen ? (
                <ChevronUp className="w-4 h-4" />
              ) : (
                <ChevronDown className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>

        {/* Console Body */}
        {isOpen && (
          <div className="p-3 bg-slate-950 font-mono text-[11px] leading-relaxed max-h-48 overflow-y-auto space-y-1 divide-y divide-slate-900">
            {displayedLogs.length === 0 ? (
              <div className="text-slate-600 italic py-2 text-center text-xs">
                Поки що немає записів у журналі...
              </div>
            ) : (
              displayedLogs.map((entry, idx) => {
                let badgeClass = "text-slate-400";
                let Icon = Info;
                if (entry.level === "ERROR") {
                  badgeClass = "text-rose-400 font-bold";
                  Icon = AlertTriangle;
                } else if (entry.level === "WARN") {
                  badgeClass = "text-amber-400 font-semibold";
                  Icon = AlertTriangle;
                } else if (entry.level === "INFO") {
                  badgeClass = "text-emerald-400";
                }

                return (
                  <div
                    key={`${entry.timestamp}-${entry.source}-${idx}`}
                    className="flex items-start gap-2 pt-1 pb-0.5 hover:bg-slate-900/50 px-1.5 rounded transition-colors"
                  >
                    <span className="text-slate-600 shrink-0 select-none">
                      {entry.timestamp}
                    </span>
                    <span
                      className={`inline-flex items-center gap-1 uppercase tracking-wider shrink-0 ${badgeClass}`}
                    >
                      <Icon className="w-3 h-3" />
                      [{entry.level}]
                    </span>
                    <span className="text-slate-500 shrink-0">
                      [{entry.source}]
                    </span>
                    <span className="text-slate-300 break-words flex-1">
                      {entry.message}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>
    </div>
  );
});
