# Gemini Live Duo Translator (macOS Desktop)

Двосторонній синхронний AI-перекладач у реальному часі для онлайн-дзвінків (**Zoom**, **Google Meet**, **Microsoft Teams**) та перегляду відео (**YouTube**). Побудований на базі **Tauri 2.0**, **React 18 (TypeScript + Tailwind CSS)**, **FastAPI (Python 3.11+)** та **Gemini 3.5 Live Translate (`gemini-3.5-live-translate-preview`)**.

---

## 🌟 Основні можливості

- **Повний дуплекс для дзвінків (Full Duplex Live Calls)**:
  - **Мій голос (UA → Обрана мова)**: Захоплює ваш голос із мікрофона, синхронно перекладає на мову співрозмовника та транслює **чистий синтезований AI-голос** у віртуальний мікрофон для Zoom/Google Meet.
  - **Звук дзвінка (Обрана мова → UA)**: Захоплює звук співрозмовника, перекладає українською, приглушує оригінал (Sidechain Audio Ducking) та виводить у ваші навушники.
- **Вкладка тестування (Demo Playground)**:
  - 3 вбудовані 16kHz WAV-записи англійською мовою (*IT Daily Standup*, *System Architecture Interview*, *Casual Small Talk*) для миттєвої перевірки розпізнавання, перекладу та синтезу без налаштування віртуальних кабелів чи дзвінків.
- **Спрощений вибір мови**:
  - Єдиний селектор «Мова співрозмовника» (English, German, Polish, Spanish, French, Italian, Japanese, Chinese). Ваша мова завжди Українська.
- **Жива телеметрія (20 FPS WebSocket)**:
  - VU-індикатори рівнів гучності, статус Ducking та синхронні двомовні текстові транскрипти.

---

## 🏗️ Архітектура системи

```text
myProject/
├── src-tauri/                 # Tauri 2.0 (Rust нативна обгортка для macOS)
├── src/                       # React 18 UI (TypeScript, Tailwind CSS, Lucide)
│   ├── components/            # Модульні компоненти (CallView, TestingView, VuMeter, TranscriptBox)
│   ├── App.tsx                # Головний компонент із вкладками дзвінка та тестування
│   └── api.ts                 # HTTP та WebSocket клієнт до бекенду
├── backend/                   # Python FastAPI Sidecar
│   ├── audio_engine.py        # DualChannelAudioEngine (PyAudio, дуплексні потоки, Ducking)
│   ├── ai_pipeline.py         # GeminiLiveAudioSession (Gemini 3.5 Live Translate)
│   ├── main.py                # FastAPI HTTP + WebSocket роути
│   ├── samples/               # Вбудовані тестові WAV-файли (16kHz mono)
│   └── requirements.txt       # Python залежності
└── package.json               # Node.js конфігурація
```

---

## 📋 Системні вимоги (macOS)

1. **PortAudio** (необхідний для `pyaudio`):
   ```bash
   brew install portaudio
   ```
2. **Node.js** (v18+) та **npm**
3. **Python** (3.11 або новіший)
4. **Rust & Cargo** (для збірки нативного застосунку Tauri):
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   ```
5. **BlackHole 2ch Virtual Audio Driver** (для перехоплення звуку із Zoom/Meet/YouTube):
   ```bash
   brew install blackhole-2ch
   ```

---

## 🚀 Покрокова інструкція із запуску

### Крок 1: Клонування та налаштування оточення

Перейдіть у кореневу директорію проєкту та налаштуйте API ключ Gemini:
```bash
# Скопіюйте приклад .env у папку backend (або введіть ключ безпосередньо в UI)
echo "GEMINI_API_KEY=ваш_ключ_gemini" > backend/.env
```

---

### Крок 2: Запуск Python бекенду

У **першому терміналі**:
```bash
cd backend

# Створення та активація віртуального оточення
python3 -m venv venv
source venv/bin/activate

# Встановлення залежностей
pip install -r requirements.txt

# Запуск сервера FastAPI (порт 8000)
python main.py
```
> Бекенд запуститься на `http://127.0.0.1:8000` з WebSocket за адресою `ws://127.0.0.1:8000/ws`.

---

### Крок 3: Запуск графічного інтерфейсу (Frontend / Tauri)

У **другому терміналі** (з кореневої папки проєкту):
```bash
# Встановлення Node-пакетів
npm install

# Варіант A: Запуск у браузері (швидкий режим розробки)
npm run dev
# Відкрийте браузер за адресою: http://localhost:1420

# Варіант B: Запуск як нативного macOS вікна (Tauri)
npm run tauri dev
```

---

## 🎧 Інструкція з використання

### 1. Вкладка «Тестування записів (Demo Playground)»
1. Перейдіть на вкладку **«Тестування записів»**.
2. Оберіть один із трьох готових аудіозаписів:
   - **IT Daily Standup** (статус розробки, мікросервіси, WebSockets).
   - **System Architecture Interview** (розподілені потоки, гео-відмовостійкість).
   - **Casual Small Talk** (плани на вихідні, розмова про погоду).
3. Виберіть ваші навушники у полі **Пристрій виводу**.
4. Натисніть **«Запустити тест обраного запису»** — ви почуєте оригінальну англійську доріжку, приглушену (Ducking), та чистий синхронний переклад українською мовою.

---

### 2. Вкладка «Синхронний дзвінок (Zoom / Google Meet)»
1. **Налаштування Zoom / Google Meet**:
   - **Мікрофон у Zoom/Meet**: виберіть **BlackHole 2ch**.
   - **Динаміки/Вихід у Zoom/Meet**: виберіть **BlackHole 2ch** (або окремий віртуальний кабель).
2. **Налаштування в застосунку**:
   - **Мій мікрофон**: оберіть ваш фізичний мікрофон (MacBook Mic, AirPods тощо).
   - **Віртуальний мікрофон для Zoom**: оберіть `BlackHole 2ch`.
   - **Вхід звуку із Zoom/Meet**: оберіть `BlackHole 2ch`.
   - **Мої навушники**: оберіть ваші фізичні навушники або динаміки.
   - **Мова співрозмовника**: оберіть мову (за замовчуванням Англійська).
3. Натисніть **«Запустити синхронний переклад дзвінка (Full Duplex)»**.
4. Коли ви говорите українською — у Zoom транслюється англійський AI-голос. Коли співрозмовник відповідає англійською — ви чуєте український переклад у своїх навушниках.

---

### 3. Переклад відео з YouTube
1. У системних налаштуваннях macOS (*System Settings → Sound → Output*) встановіть **BlackHole 2ch**.
2. У застосунку на вкладці **«Синхронний дзвінок»** у блоці **Звук співрозмовника**:
   - **Вхід звуку**: `BlackHole 2ch`.
   - **Мої навушники**: ваші навушники.
   - **Ducking**: встановіть рівень фону (15% – 25%).
3. Запустіть трансляцію та насолоджуйтесь українською озвучкою з приглушенням оригіналу.
