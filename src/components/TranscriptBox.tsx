import React, { useState } from "react";
import { Copy, Check } from "lucide-react";

interface TranscriptBoxProps {
  title: string;
  text: string;
  placeholder?: string;
  themeColor?: "indigo" | "emerald" | "amber" | "sky";
}

export const TranscriptBox: React.FC<TranscriptBoxProps> = ({
  title,
  text,
  placeholder = "Очікування аудіопотоку...",
  themeColor = "indigo",
}) => {
  const [copied, setCopied] = useState<boolean>(false);

  const colorStyles = {
    indigo: "text-indigo-400 border-indigo-900/40",
    emerald: "text-emerald-400 border-emerald-900/40",
    amber: "text-amber-400 border-amber-900/40",
    sky: "text-sky-400 border-sky-900/40",
  };

  const handleCopy = async () => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  return (
    <div className="flex-1 bg-slate-950 border border-slate-800 rounded-lg p-3 flex flex-col min-h-[110px]">
      <div className="flex items-center justify-between mb-1.5">
        <span className={`text-[11px] font-semibold uppercase tracking-wide ${colorStyles[themeColor]}`}>
          {title}
        </span>
        {text && (
          <button
            onClick={handleCopy}
            title="Скопіювати текст"
            className="text-slate-500 hover:text-slate-300 transition-colors p-0.5"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>
        )}
      </div>
      <div className="flex-1 overflow-y-auto font-mono text-xs text-slate-300 leading-relaxed max-h-[130px] pr-1">
        {text ? (
          <span className="whitespace-pre-wrap">{text}</span>
        ) : (
          <span className="text-slate-600 italic">{placeholder}</span>
        )}
      </div>
    </div>
  );
};
