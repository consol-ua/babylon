import React, { useState, useRef, useEffect, useMemo } from "react";
import { Copy, Check, Download, Trash2, X, BookOpen, FileText } from "lucide-react";
import { TranscriptItem } from "../api";

interface TranscriptBoxProps {
  title: string;
  text: string;
  history?: TranscriptItem[];
  placeholder?: string;
  themeColor?: "indigo" | "emerald" | "amber" | "sky";
  onClear?: () => void;
}

type FontSize = "sm" | "base" | "lg" | "xl";

const COLOR_STYLES = {
  indigo: "text-indigo-400 border-indigo-900/40",
  emerald: "text-emerald-400 border-emerald-900/40",
  amber: "text-amber-400 border-amber-900/40",
  sky: "text-sky-400 border-sky-900/40",
};

const FONT_SIZE_CLASSES: Record<FontSize, string> = {
  sm: "text-xs md:text-sm leading-relaxed",
  base: "text-sm md:text-base leading-relaxed",
  lg: "text-base md:text-lg leading-relaxed",
  xl: "text-lg md:text-xl leading-relaxed",
};

const FONT_SIZES: FontSize[] = ["sm", "base", "lg", "xl"];

export const TranscriptBox = React.memo<TranscriptBoxProps>(({
  title,
  text,
  history = [],
  placeholder = "Очікування аудіопотоку...",
  themeColor = "indigo",
  onClear,
}) => {
  const [copied, setCopied] = useState<boolean>(false);
  const [copiedAll, setCopiedAll] = useState<boolean>(false);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [fontSize, setFontSize] = useState<FontSize>("base");
  const historyEndRef = useRef<HTMLDivElement>(null);

  const handleDecreaseFont = () => {
    const currentIndex = FONT_SIZES.indexOf(fontSize);
    if (currentIndex > 0) {
      setFontSize(FONT_SIZES[currentIndex - 1]);
    }
  };

  const handleIncreaseFont = () => {
    const currentIndex = FONT_SIZES.indexOf(fontSize);
    if (currentIndex < FONT_SIZES.length - 1) {
      setFontSize(FONT_SIZES[currentIndex + 1]);
    }
  };

  // Scroll to bottom when history updates and modal is open
  useEffect(() => {
    if (isModalOpen && historyEndRef.current) {
      historyEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [history, text, isModalOpen]);

  const handleCopyLive = async () => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  // Clean formatted paragraphs without timestamps
  const paragraphs = useMemo(() => {
    if (history && history.length > 0) {
      return history.map((h) => h.text.trim()).filter(Boolean);
    }
    return text.trim() ? [text.trim()] : [];
  }, [history, text]);

  const getFullText = (): string => {
    if (paragraphs.length > 0) {
      return paragraphs.join("\n\n");
    }
    return text.trim();
  };

  const handleCopyAll = async () => {
    const full = getFullText();
    if (!full) return;
    try {
      await navigator.clipboard.writeText(full);
      setCopiedAll(true);
      setTimeout(() => setCopiedAll(false), 2000);
    } catch {
      // ignore
    }
  };

  const handleDownloadTxt = () => {
    const full = getFullText();
    if (!full) return;
    const blob = new Blob([full], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const sanitizedTitle = title.replace(/[^a-zA-Z0-9а-яА-ЯёЁіІїЇєЄґҐ_-]/g, "_").toLowerCase();
    a.download = `transcript_${sanitizedTitle}_${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const hasContent = paragraphs.length > 0 || Boolean(text);
  const fullTextContent = getFullText();
  const wordCount = fullTextContent ? fullTextContent.split(/\s+/).filter(Boolean).length : 0;
  const charCount = fullTextContent.length;

  return (
    <>
      <div className="flex-1 bg-slate-950 border border-slate-800 rounded-lg p-3 flex flex-col min-h-[115px]">
        {/* Header Bar */}
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-2">
            <span className={`text-[11px] font-semibold uppercase tracking-wide ${COLOR_STYLES[themeColor]}`}>
              {title}
            </span>
            {text && (
              <span className="flex items-center gap-1 text-[10px] text-emerald-400 font-medium px-1.5 py-0.2 rounded bg-emerald-950/60 border border-emerald-800/40">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                Live
              </span>
            )}
          </div>

          <div className="flex items-center gap-1.5">
            {/* Expand Full History Button */}
            <button
              type="button"
              onClick={() => setIsModalOpen(true)}
              title="Читати повний текст"
              className="flex items-center gap-1.5 text-[11px] text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 transition-colors px-2 py-0.5 rounded border border-slate-800"
            >
              <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
              <span>Читати текст</span>
              {paragraphs.length > 0 && (
                <span className="text-[10px] font-mono font-bold bg-indigo-900/60 text-indigo-300 px-1 rounded">
                  {paragraphs.length}
                </span>
              )}
            </button>

            {/* Quick Copy Live Button */}
            {text && (
              <button
                type="button"
                onClick={handleCopyLive}
                title="Скопіювати поточну фразу"
                className="text-slate-500 hover:text-slate-300 transition-colors p-1 rounded hover:bg-slate-800"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
            )}
          </div>
        </div>

        {/* Live Text Body */}
        <div className="flex-1 overflow-y-auto font-mono text-xs text-slate-300 leading-relaxed max-h-[130px] pr-1">
          {text ? (
            <span className="whitespace-pre-wrap">{text}</span>
          ) : paragraphs.length > 0 ? (
            <span className="whitespace-pre-wrap text-slate-400">
              {paragraphs[paragraphs.length - 1]}
            </span>
          ) : (
            <span className="text-slate-600 italic">{placeholder}</span>
          )}
        </div>
      </div>

      {/* Full Transcript Reader Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-slate-950/85 backdrop-blur-md z-50 flex items-center justify-center p-4 sm:p-6 animate-fadeIn">
          <div className="bg-slate-900 border border-slate-700/90 rounded-2xl w-full max-w-3xl shadow-2xl flex flex-col max-h-[85vh] overflow-hidden">
            {/* Modal Header & Toolbar */}
            <div className="flex flex-wrap items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/60 gap-3">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                  <BookOpen className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
                    {title}
                    <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                      {paragraphs.length} {paragraphs.length === 1 ? "абзац" : "абзаців"}
                    </span>
                  </h3>
                  <p className="text-[11px] text-slate-400">
                    Зручний режим читання повного тексту
                  </p>
                </div>
              </div>

              {/* Action Toolbar */}
              <div className="flex items-center gap-2">
                {/* Font Size Adjuster */}
                <div className="flex items-center bg-slate-800/80 rounded-lg p-0.5 border border-slate-700">
                  <button
                    type="button"
                    onClick={handleDecreaseFont}
                    title="Зменшити розмір шрифту"
                    disabled={fontSize === "sm"}
                    className="px-2 py-1 text-xs font-bold text-slate-300 hover:text-white hover:bg-slate-700 rounded transition disabled:opacity-30"
                  >
                    A-
                  </button>
                  <span className="text-[10px] uppercase font-mono px-1.5 text-slate-400 select-none">
                    {fontSize}
                  </span>
                  <button
                    type="button"
                    onClick={handleIncreaseFont}
                    title="Збільшити розмір шрифту"
                    disabled={fontSize === "xl"}
                    className="px-2 py-1 text-xs font-bold text-slate-300 hover:text-white hover:bg-slate-700 rounded transition disabled:opacity-30"
                  >
                    A+
                  </button>
                </div>

                {hasContent && (
                  <>
                    <button
                      type="button"
                      onClick={handleCopyAll}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition shadow-sm"
                      title="Скопіювати весь текст без таймстемпів"
                    >
                      {copiedAll ? (
                        <>
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                          <span className="text-emerald-400">Скопійовано</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3.5 h-3.5" />
                          <span>Скопіювати</span>
                        </>
                      )}
                    </button>

                    <button
                      type="button"
                      onClick={handleDownloadTxt}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 text-xs font-medium border border-indigo-500/40 transition"
                      title="Зберегти текст у файл TXT"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>TXT</span>
                    </button>

                    {onClear && (
                      <button
                        type="button"
                        onClick={onClear}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition"
                        title="Очистити історію"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </>
                )}

                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition ml-1"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Modal Body: Book / Article Reader View */}
            <div className={`flex-1 overflow-y-auto p-6 md:p-8 space-y-4 bg-slate-950/70 ${FONT_SIZE_CLASSES[fontSize]} font-sans selection:bg-indigo-500/30`}>
              {paragraphs.length > 0 ? (
                <>
                  {paragraphs.map((pText, idx) => (
                    <p
                      key={idx}
                      className="text-slate-200 tracking-normal leading-relaxed text-justify"
                    >
                      {pText}
                    </p>
                  ))}
                  <div ref={historyEndRef} />
                </>
              ) : text ? (
                <p className="text-slate-200 tracking-normal leading-relaxed">
                  {text}
                </p>
              ) : (
                <div className="h-48 flex flex-col items-center justify-center text-slate-500 text-sm">
                  <FileText className="w-8 h-8 text-slate-700 mb-2" />
                  <span>Текст транскрипції порожній. Говоріть або запустіть запис.</span>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3.5 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between text-xs text-slate-400">
              <div className="flex items-center gap-4">
                <span>
                  Слів: <strong className="text-slate-200 font-mono">{wordCount}</strong>
                </span>
                <span>
                  Символів: <strong className="text-slate-200 font-mono">{charCount}</strong>
                </span>
              </div>

              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium text-xs transition"
              >
                Закрити
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}, (prev, next) => {
  return prev.text === next.text && 
         prev.history?.length === next.history?.length &&
         prev.title === next.title &&
         prev.themeColor === next.themeColor;
});
