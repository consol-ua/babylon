import React, { useState, useCallback, useMemo } from "react";
import { Plus, Sparkles, Cloud, Cpu, Mic, Trash2, Volume2 } from "lucide-react";
import { VoiceMode, VoiceProfile, VoiceSelection } from "../../types/voice";
import { useVoiceProfiles } from "../../hooks/useVoiceProfiles";
import { VoiceProfileModal } from "./VoiceProfileModal";

export interface VoiceSelectorProps {
  value: VoiceSelection;
  onChange: (val: VoiceSelection) => void;
  language: string;
  label?: string;
  disabled?: boolean;
  className?: string;
  showPreview?: boolean;
}

export const VoiceSelector: React.FC<VoiceSelectorProps> = React.memo(({
  value,
  onChange,
  language,
  label = "Голос синтезу (TTS)",
  disabled = false,
  className = "",
  showPreview = false,
}) => {
  const { categorizedVoices, refreshVoices, deleteProfile, testSynthesize, playAudio } =
    useVoiceProfiles();

  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);
  const [isPreviewing, setIsPreviewing] = useState<boolean>(false);

  // Grouped and language-prioritized local voices
  const sortedLocalVoices = useMemo(() => {
    const list = [...categorizedVoices.local];
    // Prioritize voices matching target language
    return list.sort((a, b) => {
      const aMatches = a.language.toLowerCase() === language.toLowerCase();
      const bMatches = b.language.toLowerCase() === language.toLowerCase();
      if (aMatches && !bMatches) return -1;
      if (!aMatches && bMatches) return 1;
      return a.name.localeCompare(b.name);
    });
  }, [categorizedVoices.local, language]);

  // Current serialized value for select element: "mode:voice_id"
  const currentSelectKey = useMemo(() => {
    return `${value.mode}:${value.voice_id}`;
  }, [value.mode, value.voice_id]);

  // Handle dropdown selection change
  const handleSelectChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const rawValue = e.target.value;
      if (!rawValue) return;

      const [modeStr, ...idParts] = rawValue.split(":");
      const mode = modeStr as VoiceMode;
      const voice_id = idParts.join(":");

      onChange({ mode, voice_id });
    },
    [onChange]
  );

  // Profile creation callback from modal
  const handleProfileCreated = useCallback(
    (newProfile: VoiceProfile) => {
      onChange({ mode: "cloned", voice_id: newProfile.id });
      void refreshVoices();
    },
    [onChange, refreshVoices]
  );

  // Optional: delete selected cloned profile
  const handleDeleteCurrentCloned = useCallback(async () => {
    if (value.mode !== "cloned" || !value.voice_id) return;

    const confirmed = window.confirm(
      "Ви впевнені, що хочете видалити цей клонований голосовий профіль?"
    );
    if (!confirmed) return;

    setIsDeleting(true);
    try {
      await deleteProfile(value.voice_id);
      // Fall back to first available cloud voice
      const fallbackVoice = categorizedVoices.cloud[0]?.id || "Puck";
      onChange({ mode: "cloud", voice_id: fallbackVoice });
    } catch (err) {
      console.error("[VoiceSelector] Failed to delete voice profile:", err);
    } finally {
      setIsDeleting(false);
    }
  }, [value.mode, value.voice_id, deleteProfile, categorizedVoices.cloud, onChange]);

  // Optional: Quick preview playback of currently selected voice
  const handleQuickPreview = useCallback(async () => {
    setIsPreviewing(true);
    try {
      const previewPhrase =
        language === "uk"
          ? "Привіт! Це приклад звучання вибраного голосу."
          : "Hello! This is a preview of the selected voice.";

      const res = await testSynthesize({
        text: previewPhrase,
        mode: value.mode,
        voice_id: value.voice_id,
        language,
      });

      await playAudio(res.audioUrl);
    } catch (err) {
      console.warn("[VoiceSelector] Quick preview error:", err);
    } finally {
      setIsPreviewing(false);
    }
  }, [language, testSynthesize, value.mode, value.voice_id, playAudio]);

  // Badge icon according to active voice mode
  const modeBadge = useMemo(() => {
    switch (value.mode) {
      case "cloud":
        return {
          icon: <Cloud className="w-3 h-3 text-sky-400" />,
          label: "Cloud Gemini",
          colorClass: "bg-sky-950/60 text-sky-300 border-sky-800/60",
        };
      case "local":
        return {
          icon: <Cpu className="w-3 h-3 text-emerald-400" />,
          label: "Local ONNX",
          colorClass: "bg-emerald-950/60 text-emerald-300 border-emerald-800/60",
        };
      case "cloned":
        return {
          icon: <Mic className="w-3 h-3 text-indigo-400" />,
          label: "Zero-Shot Clone",
          colorClass: "bg-indigo-950/60 text-indigo-300 border-indigo-800/60",
        };
    }
  }, [value.mode]);

  return (
    <div className={`space-y-1.5 ${className}`}>
      {/* Label and Badge Header */}
      <div className="flex items-center justify-between">
        <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
          {label}
        </label>
        <div
          className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold border ${modeBadge.colorClass}`}
        >
          {modeBadge.icon}
          <span>{modeBadge.label}</span>
        </div>
      </div>

      {/* Main Selector Row: Dropdown + Clone Button */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <select
            value={currentSelectKey}
            onChange={handleSelectChange}
            disabled={disabled}
            className="w-full appearance-none bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-100 font-medium focus:outline-none focus:border-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed pr-8 cursor-pointer"
          >
            {/* 1. Cloud Voices */}
            <optgroup label="☁️ Хмарні голоси Gemini (Ultra Low Latency)">
              {categorizedVoices.cloud.map((v) => (
                <option key={`cloud:${v.id}`} value={`cloud:${v.id}`}>
                  {v.label}
                </option>
              ))}
            </optgroup>

            {/* 2. Local Neural TTS (Piper ONNX) */}
            <optgroup label="💻 Локальні нейромережі (Piper ONNX)">
              {sortedLocalVoices.map((v) => (
                <option key={`local:${v.id}`} value={`local:${v.id}`}>
                  {v.name} ({v.language.toUpperCase()})
                  {v.description ? ` - ${v.description}` : ""}
                </option>
              ))}
            </optgroup>

            {/* 3. Cloned Profiles */}
            <optgroup label="🎙️ Клоновані голоси (Користувацькі профілі)">
              {categorizedVoices.cloned.length > 0 ? (
                categorizedVoices.cloned.map((p) => (
                  <option key={`cloned:${p.id}`} value={`cloned:${p.id}`}>
                    {p.name} ({p.language.toUpperCase()})
                  </option>
                ))
              ) : (
                <option value="" disabled>
                  (Немає клонованих профілів. Натисніть «+ Клонувати»)
                </option>
              )}
            </optgroup>
          </select>

          {/* Custom chevron indicator */}
          <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2.5 text-slate-400">
            <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 20 20">
              <path
                d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
                clipRule="evenodd"
                fillRule="evenodd"
              />
            </svg>
          </div>
        </div>

        {/* Action Buttons: Preview (Optional), Delete (If cloned), Clone Modal */}
        {showPreview && (
          <button
            type="button"
            onClick={() => void handleQuickPreview()}
            disabled={disabled || isPreviewing}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 hover:text-slate-100 transition-colors disabled:opacity-50"
            title="Прослухати зразок голосу"
          >
            <Volume2 className="w-4 h-4 text-indigo-400" />
          </button>
        )}

        {value.mode === "cloned" && (
          <button
            type="button"
            onClick={() => void handleDeleteCurrentCloned()}
            disabled={disabled || isDeleting}
            className="p-2 rounded-lg bg-slate-800 hover:bg-rose-900/50 border border-slate-700 hover:border-rose-800 text-slate-400 hover:text-rose-300 transition-colors disabled:opacity-50"
            title="Видалити цей голосовий профіль"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        )}

        {/* Small + Клонувати button */}
        <button
          type="button"
          onClick={() => setIsModalOpen(true)}
          disabled={disabled}
          className="flex items-center gap-1.5 px-2.5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 text-white text-xs font-semibold shrink-0 transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
          title="Створити новий клонований голосовий профіль"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>+ Клонувати</span>
        </button>
      </div>

      {/* VoiceProfileModal */}
      <VoiceProfileModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onProfileCreated={handleProfileCreated}
        initialLanguage={language}
      />
    </div>
  );
});

VoiceSelector.displayName = "VoiceSelector";
