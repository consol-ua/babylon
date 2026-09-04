import React, { useState, useCallback, useRef, useEffect, useMemo } from "react";
import {
  X,
  Mic,
  Upload,
  Sparkles,
  Play,
  Pause,
  Loader2,
  FileAudio,
  Trash2,
  AlertCircle,
  Check,
} from "lucide-react";
import { AudioRecorderWidget } from "./AudioRecorderWidget";
import { useVoiceProfiles } from "../../hooks/useVoiceProfiles";
import { VoiceProfile } from "../../types/voice";

export interface VoiceProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
  onProfileCreated?: (profile: VoiceProfile) => void;
  initialLanguage?: string;
}

interface LanguageOptionItem {
  code: string;
  name: string;
  flag: string;
}

const VOICE_LANGUAGES: LanguageOptionItem[] = [
  { code: "uk", name: "Українська", flag: "🇺🇦" },
  { code: "en", name: "English", flag: "🇺🇸" },
  { code: "pl", name: "Polski", flag: "🇵🇱" },
  { code: "de", name: "Deutsch", flag: "🇩🇪" },
  { code: "es", name: "Español", flag: "🇪🇸" },
  { code: "fr", name: "Français", flag: "🇫🇷" },
];

export const VoiceProfileModal: React.FC<VoiceProfileModalProps> = React.memo(({
  isOpen,
  onClose,
  onProfileCreated,
  initialLanguage = "uk",
}) => {
  const { createProfile, uploadSample, testSynthesize } = useVoiceProfiles();

  const [name, setName] = useState<string>("");
  const [language, setLanguage] = useState<string>(initialLanguage);
  const [activeTab, setActiveTab] = useState<"record" | "upload">("record");

  // Audio sample states
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [recordedDuration, setRecordedDuration] = useState<number>(0);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [uploadedAudioUrl, setUploadedAudioUrl] = useState<string | null>(null);
  const [isPlayingUploaded, setIsPlayingUploaded] = useState<boolean>(false);
  const [isDragOver, setIsDragOver] = useState<boolean>(false);

  // Test Synthesis States
  const [testPhrase, setTestPhrase] = useState<string>(
    "Привіт! Це демонстраційний зразок мого клонованого голосу для синхронного перекладу."
  );
  const [isSynthesizingTest, setIsSynthesizingTest] = useState<boolean>(false);
  const [testAudioUrl, setTestAudioUrl] = useState<string | null>(null);
  const [isPlayingTest, setIsPlayingTest] = useState<boolean>(false);

  // Submission States
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Audio element references for playback
  const testAudioRef = useRef<HTMLAudioElement | null>(null);
  const uploadedAudioRef = useRef<HTMLAudioElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Update default test phrase based on chosen language
  useEffect(() => {
    if (language === "uk") {
      setTestPhrase("Привіт! Це демонстраційний зразок мого клонованого голосу для синхронного перекладу.");
    } else if (language === "en") {
      setTestPhrase("Hello! This is a test demonstration of my cloned voice for simultaneous translation.");
    } else if (language === "pl") {
      setTestPhrase("Cześć! To jest próbka mojego sklonowanego głosu do tłumaczenia symultanicznego.");
    } else if (language === "de") {
      setTestPhrase("Hallo! Dies ist ein Test meiner geklonten Stimme für die Simultandolmetschung.");
    }
  }, [language]);

  // Clean up audio objects on close/unmount
  const cleanupAudios = useCallback(() => {
    if (testAudioRef.current) {
      testAudioRef.current.pause();
      testAudioRef.current = null;
    }
    if (uploadedAudioRef.current) {
      uploadedAudioRef.current.pause();
      uploadedAudioRef.current = null;
    }
    if (uploadedAudioUrl) {
      URL.revokeObjectURL(uploadedAudioUrl);
      setUploadedAudioUrl(null);
    }
    if (testAudioUrl && !testAudioUrl.startsWith("http")) {
      URL.revokeObjectURL(testAudioUrl);
      setTestAudioUrl(null);
    }
    setIsPlayingTest(false);
    setIsPlayingUploaded(false);
  }, [uploadedAudioUrl, testAudioUrl]);

  // Handle modal close
  const handleModalClose = useCallback(() => {
    if (isSaving) return;
    cleanupAudios();
    setName("");
    setRecordedBlob(null);
    setRecordedDuration(0);
    setUploadedFile(null);
    setErrorMessage(null);
    onClose();
  }, [isSaving, cleanupAudios, onClose]);

  // Escape key listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen && !isSaving) {
        handleModalClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isSaving, handleModalClose]);

  // Recording callback
  const handleAudioRecorded = useCallback((blob: Blob, duration: number) => {
    setRecordedBlob(blob);
    setRecordedDuration(duration);
    setErrorMessage(null);
  }, []);

  // File Upload Handlers
  const handleFileSelect = useCallback((file: File) => {
    if (!file.type.startsWith("audio/") && !file.name.match(/\.(wav|mp3|m4a|ogg|flac)$/i)) {
      setErrorMessage("Будь ласка, оберіть аудіофайл (.wav, .mp3, .m4a, .ogg)");
      return;
    }
    if (file.size > 30 * 1024 * 1024) {
      setErrorMessage("Розмір файлу не повинен перевищувати 30 МБ");
      return;
    }

    if (uploadedAudioUrl) {
      URL.revokeObjectURL(uploadedAudioUrl);
    }
    const url = URL.createObjectURL(file);
    setUploadedFile(file);
    setUploadedAudioUrl(url);
    setErrorMessage(null);
  }, [uploadedAudioUrl]);

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFileSelect(e.target.files[0]);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleRemoveUploadedFile = useCallback(() => {
    if (uploadedAudioRef.current) {
      uploadedAudioRef.current.pause();
      uploadedAudioRef.current = null;
      setIsPlayingUploaded(false);
    }
    if (uploadedAudioUrl) {
      URL.revokeObjectURL(uploadedAudioUrl);
      setUploadedAudioUrl(null);
    }
    setUploadedFile(null);
  }, [uploadedAudioUrl]);

  const togglePlayUploaded = useCallback(() => {
    if (!uploadedAudioUrl) return;

    if (isPlayingUploaded) {
      if (uploadedAudioRef.current) {
        uploadedAudioRef.current.pause();
        uploadedAudioRef.current.currentTime = 0;
      }
      setIsPlayingUploaded(false);
    } else {
      const audio = new Audio(uploadedAudioUrl);
      uploadedAudioRef.current = audio;
      setIsPlayingUploaded(true);

      audio.onended = () => {
        setIsPlayingUploaded(false);
        uploadedAudioRef.current = null;
      };

      audio.onerror = () => {
        setIsPlayingUploaded(false);
        uploadedAudioRef.current = null;
      };

      void audio.play().catch(() => {
        setIsPlayingUploaded(false);
        uploadedAudioRef.current = null;
      });
    }
  }, [uploadedAudioUrl, isPlayingUploaded]);

  // Test Synthesize Playback
  const handleTestSynthesize = useCallback(async () => {
    if (!testPhrase.trim()) return;

    setIsSynthesizingTest(true);
    setErrorMessage(null);

    try {
      // If we already have a sample, invoke test-synthesize endpoint
      const result = await testSynthesize({
        text: testPhrase.trim(),
        voice_id: name.trim() || "preview_clone",
        mode: "cloned",
        language,
      });

      setTestAudioUrl(result.audioUrl);

      // Immediately play test result
      if (testAudioRef.current) {
        testAudioRef.current.pause();
      }
      const audio = new Audio(result.audioUrl);
      testAudioRef.current = audio;
      setIsPlayingTest(true);

      audio.onended = () => {
        setIsPlayingTest(false);
        testAudioRef.current = null;
      };

      audio.onerror = () => {
        setIsPlayingTest(false);
        testAudioRef.current = null;
      };

      await audio.play();
    } catch (err) {
      console.warn("[VoiceProfileModal] Test synthesize note:", err);
      // If server test-synthesize fails, fallback to playing user reference audio if available
      const fallbackUrl =
        activeTab === "record" && recordedBlob
          ? URL.createObjectURL(recordedBlob)
          : uploadedAudioUrl;

      if (fallbackUrl) {
        if (testAudioRef.current) {
          testAudioRef.current.pause();
        }
        const audio = new Audio(fallbackUrl);
        testAudioRef.current = audio;
        setIsPlayingTest(true);

        audio.onended = () => {
          setIsPlayingTest(false);
          testAudioRef.current = null;
        };

        await audio.play().catch(() => {
          setIsPlayingTest(false);
        });
      } else {
        setErrorMessage("Для перевірки спочатку запишіть або завантажте аудіозразок.");
      }
    } finally {
      setIsSynthesizingTest(false);
    }
  }, [testPhrase, testSynthesize, name, language, activeTab, recordedBlob, uploadedAudioUrl]);

  // Stop test audio
  const handleToggleTestPlayback = useCallback(() => {
    if (!testAudioUrl) return;

    if (isPlayingTest) {
      if (testAudioRef.current) {
        testAudioRef.current.pause();
      }
      setIsPlayingTest(false);
    } else {
      if (testAudioRef.current) {
        void testAudioRef.current.play();
        setIsPlayingTest(true);
      } else {
        const audio = new Audio(testAudioUrl);
        testAudioRef.current = audio;
        setIsPlayingTest(true);
        audio.onended = () => {
          setIsPlayingTest(false);
          testAudioRef.current = null;
        };
        void audio.play();
      }
    }
  }, [testAudioUrl, isPlayingTest]);

  // Check validity for saving
  const hasSample = useMemo(() => {
    return activeTab === "record" ? recordedBlob !== null : uploadedFile !== null;
  }, [activeTab, recordedBlob, uploadedFile]);

  const canSave = useMemo(() => {
    return name.trim().length > 0 && hasSample && !isSaving;
  }, [name, hasSample, isSaving]);

  // Save profile and upload sample
  const handleSave = useCallback(async () => {
    if (!canSave) return;

    setIsSaving(true);
    setErrorMessage(null);

    try {
      // 1. Create Profile
      const newProfile = await createProfile({
        name: name.trim(),
        language,
        engine_type: "cloned",
      });

      // 2. Upload Sample
      let sampleData: Blob | File;
      let filename: string;

      if (activeTab === "record" && recordedBlob) {
        sampleData = recordedBlob;
        filename = `${newProfile.id}_sample.webm`;
      } else if (activeTab === "upload" && uploadedFile) {
        sampleData = uploadedFile;
        filename = uploadedFile.name;
      } else {
        throw new Error("Не знайдено аудіозапису для завантаження");
      }

      const updatedProfile = await uploadSample(newProfile.id, sampleData, filename);

      onProfileCreated?.(updatedProfile);
      handleModalClose();
    } catch (err) {
      console.error("[VoiceProfileModal] Save error:", err);
      const msg = err instanceof Error ? err.message : "Не вдалося зберегти профіль голосу";
      setErrorMessage(msg);
    } finally {
      setIsSaving(false);
    }
  }, [
    canSave,
    createProfile,
    name,
    language,
    activeTab,
    recordedBlob,
    uploadedFile,
    uploadSample,
    onProfileCreated,
    handleModalClose,
  ]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fadeIn">
      <div
        className="relative w-full max-w-xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-100">
                Новий голосовий профіль / Клонування
              </h2>
              <p className="text-xs text-slate-400">
                Zero-Shot клонування голосу за коротким аудіозразком (5-10 сек)
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleModalClose}
            disabled={isSaving}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors disabled:opacity-50"
            title="Закрити"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-5 text-sm">
          {/* Error Banner */}
          {errorMessage && (
            <div className="flex items-center gap-2.5 p-3 rounded-xl bg-rose-950/50 border border-rose-800/60 text-rose-300 text-xs animate-fadeIn">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {/* Profile Name & Language Form Row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                Назва профілю
                <span className="text-rose-400">*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Мій голос (Zoom / Call)"
                disabled={isSaving}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                Мова профілю
                <span className="text-rose-400">*</span>
              </label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                disabled={isSaving}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-100 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
              >
                {VOICE_LANGUAGES.map((lang) => (
                  <option key={lang.code} value={lang.code}>
                    {lang.flag} {lang.name} ({lang.code.toUpperCase()})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Sample Source Selection Tabs */}
          <div className="space-y-2.5">
            <label className="text-xs font-semibold text-slate-300">
              Джерело зразка голосу (5–10 секунд)
            </label>
            <div className="flex rounded-lg bg-slate-950 border border-slate-800 p-1 gap-1">
              <button
                type="button"
                onClick={() => setActiveTab("record")}
                disabled={isSaving}
                className={`flex-1 flex items-center justify-center gap-2 py-1.5 rounded-md text-xs font-semibold transition-all ${
                  activeTab === "record"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Mic className="w-3.5 h-3.5" />
                Записати з мікрофона
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("upload")}
                disabled={isSaving}
                className={`flex-1 flex items-center justify-center gap-2 py-1.5 rounded-md text-xs font-semibold transition-all ${
                  activeTab === "upload"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Upload className="w-3.5 h-3.5" />
                Завантажити аудіофайл
              </button>
            </div>
          </div>

          {/* Active Tab Content */}
          {activeTab === "record" ? (
            <AudioRecorderWidget
              onAudioRecorded={handleAudioRecorded}
              minDurationSeconds={5}
              maxDurationSeconds={10}
              disabled={isSaving}
            />
          ) : (
            <div className="space-y-3">
              {/* File Drag and Drop Zone */}
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragOver(true);
                }}
                onDragLeave={() => setIsDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors flex flex-col items-center justify-center gap-2.5 ${
                  isDragOver
                    ? "border-indigo-500 bg-indigo-950/20"
                    : uploadedFile
                    ? "border-emerald-500/50 bg-slate-950/60"
                    : "border-slate-800 hover:border-slate-700 bg-slate-950/40"
                }`}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileInputChange}
                  accept=".wav,.mp3,.m4a,.ogg,.flac,audio/*"
                  className="hidden"
                />

                <div className="p-3 rounded-full bg-slate-800 text-indigo-400">
                  <FileAudio className="w-6 h-6" />
                </div>

                <div>
                  <p className="text-xs font-semibold text-slate-200">
                    {uploadedFile
                      ? uploadedFile.name
                      : "Натисніть або перетягніть аудіофайл сюди"}
                  </p>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Підтримуються .wav, .mp3, .m4a (рекомендовано 5–15 сек чистої мови)
                  </p>
                </div>
              </div>

              {/* Uploaded File Details & Preview */}
              {uploadedFile && (
                <div className="flex items-center justify-between p-3 rounded-xl bg-slate-950 border border-slate-800">
                  <div className="flex items-center gap-2.5 overflow-hidden">
                    <FileAudio className="w-4 h-4 text-emerald-400 shrink-0" />
                    <div className="truncate">
                      <span className="text-xs text-slate-200 font-medium truncate block">
                        {uploadedFile.name}
                      </span>
                      <span className="text-[10px] text-slate-400">
                        {(uploadedFile.size / 1024).toFixed(1)} KB
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={togglePlayUploaded}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold"
                    >
                      {isPlayingUploaded ? (
                        <>
                          <Pause className="w-3 h-3 fill-current" /> Пауза
                        </>
                      ) : (
                        <>
                          <Play className="w-3 h-3 fill-current" /> Прослухати
                        </>
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={handleRemoveUploadedFile}
                      className="p-1 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition-colors"
                      title="Видалити файл"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Test Synthesize Section */}
          <div className="pt-3 border-t border-slate-800 space-y-2.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                Тестова фраза для синтезу
              </label>
              {testAudioUrl && (
                <button
                  type="button"
                  onClick={handleToggleTestPlayback}
                  className="text-xs text-indigo-400 hover:text-indigo-300 font-medium flex items-center gap-1"
                >
                  {isPlayingTest ? (
                    <>
                      <Pause className="w-3 h-3 fill-current" /> Зупинити аудіо
                    </>
                  ) : (
                    <>
                      <Play className="w-3 h-3 fill-current" /> Прослухати тест
                    </>
                  )}
                </button>
              )}
            </div>

            <div className="flex gap-2">
              <input
                type="text"
                value={testPhrase}
                onChange={(e) => setTestPhrase(e.target.value)}
                placeholder="Введіть тестову фразу..."
                disabled={isSaving || isSynthesizingTest}
                className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 disabled:opacity-50"
              />
              <button
                type="button"
                onClick={() => void handleTestSynthesize()}
                disabled={isSaving || isSynthesizingTest || !hasSample}
                className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
              >
                {isSynthesizingTest ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" />
                    Генеруємо...
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5" />
                    Прослухати тест
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-800 bg-slate-950/60">
          <div className="text-[11px] text-slate-400">
            {hasSample ? (
              <span className="text-emerald-400 flex items-center gap-1">
                <Check className="w-3.5 h-3.5" /> Зразок готовий до клонування
                {activeTab === "record" && recordedDuration > 0
                  ? ` (${recordedDuration}с)`
                  : ""}
              </span>
            ) : (
              <span className="text-amber-400">
                Потрібно надати зразок голосу (запис або файл)
              </span>
            )}
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={handleModalClose}
              disabled={isSaving}
              className="px-4 py-2 rounded-lg text-xs font-medium text-slate-300 hover:bg-slate-800 transition-colors disabled:opacity-50"
            >
              Скасувати
            </button>
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={!canSave}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
            >
              {isSaving ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Збереження...
                </>
              ) : (
                <>
                  <Check className="w-3.5 h-3.5" />
                  Зберегти профіль
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
});

VoiceProfileModal.displayName = "VoiceProfileModal";
