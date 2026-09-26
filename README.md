# AI Video Workflow v7

A macOS-native, subtitle-first AI video editing workflow and desktop studio designed for high-efficiency content production: talking-head tutorials, travel vlogs, and dual-format releases (16:9 Landscape for YouTube & 9:16 Portrait for Instagram Reels, YouTube Shorts, and TikTok).

這是一個字幕優先、AI 輔助的 macOS 本機影音剪輯工作流與桌面工作室，專為高效影片製作打造：涵蓋口播教學、旅遊生活 Vlog 以及雙格式成片輸出（16:9 橫式 YouTube 與 9:16 直式 Instagram Reels / Shorts / TikTok）。

---

## Interactive Guide / 互動操作指南

Open [`guide.html`](guide.html) directly in any browser for an interactive, bilingual step-by-step visual walkthrough featuring dark/light themes, keyboard shortcuts, bookmarking, and audio read-aloud:

直接在瀏覽器開啟 [`guide.html`](guide.html)，即可使用完整雙語互動指南：包含深淺色模式切換、鍵盤快捷鍵、個人書籤與語音朗讀。

```text
01 Setup (環境設定) → 02 Input (放入素材) → 03 AI (分析製作) → 04 Output (查看成果) → 05 Editor (編輯微調)
```

---

## 5-Step Workflow / 五步驟完整操作流程

### 01 · Setup 環境設定

Prepare the local environment before running AI transcription or rendering:
在開始本機 AI 處理前，請先準備好基礎環境與工具：

1. **System Tools (系統工具)**:
   ```bash
   # Install via Homebrew / 使用 Homebrew 安裝
   brew install python ffmpeg yt-dlp

   # Install Apple Developer CLI / 安裝 macOS 建置工具
   xcode-select --install
   ```
2. **Environment Variables & Secrets (環境變數設定)**:
   ```bash
   cp .env.example .env
   ```
   Add your `GROQ_API_KEY` into `.env` for speech-to-text transcription.
   在 `.env` 中設定 `GROQ_API_KEY` 以啟用 Whisper 快速語音辨識。
   > **Security Notice / 安全須知**: `.env` is strictly ignored by `.gitignore` and must NEVER be committed to Git. Real credentials stay 100% on your local machine.
   > `.env` 受 `.gitignore` 嚴格防護，絕不提交至 GitHub；所有真實金鑰僅存放於本機。

---

### 02 · Input 放入素材

Organize media inside project folders under `1_input/` (or `input/`):
將每部影片的素材整理於 `1_input/`（或 `input/`）專案資料夾中：

```text
1_input/
  20260925_my_project/
    001_intro.mp4
    002_highlight.jpg
    003_screen_recording.mov
```

* **Supported Formats (支援格式)**: MP4, MOV, M4V, JPG, PNG.
* **Photos as Highlights (照片重點)**: JPG/PNG photos are automatically integrated as 1.5–2.0s highlight scenes without cropping distortions. HEIC files should be converted to JPG/PNG before import.
* **Auto-Standardization (自動標準化命名)**: Files can be automatically sorted chronologically by capture metadata and renamed to `YYYYMMDD_subject_001.ext`.

---

### 03 · AI Analysis & Local Processing / AI 分析與本機製作

Invoke local pipeline agents or the native desktop controller to process the raw footage:
透過本機管線工具或桌面控制器處理原始素材：

* **Speech-to-Text (語音辨識與切句)**: Fast Whisper transcription generates accurately segmented bilingual subtitles (Chinese + English).
* **Smart Cut & Hesitation Removal (口播智慧切除)**: Automatically detects and trims repeated takes, false starts, and unnatural pauses while preserving seamless audio continuity.
* **Neural Bokeh Blur (人像景深虛化)**: Uses Apple Vision Neural Engine person segmentation to apply cinematic background blur for talking-head videos.
* **Audio Ducking (背景配樂自動閃避)**: Balances original voice audio with selected light background music, dynamically lowering music volume whenever speech is active.
* **Scene 1 Intro Card (高質感片頭封面圖)**: Generates a typography-rich opening hook graphic (1.5–2.5s) rendered via native Swift CoreText compositing.

---

### 04 · Output 查看成果

Review rendered outputs in `3_output/` (or `output/`):
在 `3_output/`（或 `output/`）查看生成的成果：

```text
3_output/
  20260925_my_project/
    20260925_my_project_v1.mp4          # 1080x1920 9:16 Vertical (直式短影音)
    20260925_my_project_v1_horizontal.mp4  # 1920x1080 16:9 Horizontal (橫式長影片)
    20260925_my_project_v1.srt          # Synchronized subtitles (同名字幕檔)
    20260925_my_project_v1.html         # Interactive review worksheet (互動審閱工作表)
```

* Rendered movies always use clean numeric versioning (`_v1.mp4`, `_v2.mp4`).
* Intermediate state, extracted audio, and cache are preserved in `2_processing/` (or `processing/`) for non-destructive re-renders.

---

### 05 · Editor 編輯器微調與二次匯出

Launch the dedicated studio editor to calibrate subtitles, adjust reframing, or trim clips:
啟動專屬桌面編輯器或離線網頁編輯器進行校對與微調：

1. **Native Desktop Editor (macOS 桌面編輯器 - 推薦)**:
   Double-click `AI Video Workflow v7.command` or run:
   ```bash
   ./"AI Video Workflow v7.command"
   ```
   * Single-page workspace: Left media sidebar, center live preview, right bilingual captions, and bottom multi-track timeline.
   * Drag-and-drop subtitle repositioning with live pointer anchor tracking.
   * Dynamic bilingual subtitle sizing: Chinese base with 40%–90% adjustable English scale (default 70%).
   * Reframing modes: Switch freely between **Crop to Fill** (center 9:16 cut) and **Full Frame + Blurred Extension**.
   * One-click dual-format re-export.

2. **Offline HTML Batch Editor (離線批次編輯器)**:
   Open `templates/editor.html` directly in your browser, or launch with local transcription capabilities:
   ```bash
   ./"AI Video Workflow v7.command" --legacy-batch
   ```

---

## Repository Structure / 目錄結構

```text
ai-video-workflow/
├── GUIDE.html                      # Interactive visual user guide (雙語互動使用指南)
├── AI Video Workflow v7.command    # One-click desktop launcher (macOS 桌面啟動器)
├── input/                          # Public folder skeleton: raw media inputs (本地素材入口)
├── processing/                     # Public folder skeleton: intermediate render state (中間處理區)
├── output/                         # Public folder skeleton: final rendered videos (成果輸出區)
├── temp/                           # Scratch and temporary conversion cache (暫存區)
├── uploads/                        # Staged upload buffer (上傳緩衝區)
├── downloads/                      # Downloaded reference media buffer (下載緩衝區)
├── 1_input/                        # Legacy/working media input directory (工作素材目錄)
├── 2_processing/                   # Working intermediate processing directory (工作處理目錄)
├── 3_output/                       # Working rendered output directory (工作成果目錄)
├── system/                         # Native macOS pipeline & desktop application
│   ├── app.py                      # Batch server application
│   ├── desktop_server.py           # Loopback controller for desktop AppKit app
│   ├── editor_export.py            # Local FFmpeg rendering bridge
│   ├── desktop/                    # Native Swift AppKit wrapper & UI assets
│   ├── pipeline/                   # Python & Swift rendering modules (CoreText, Vision)
│   └── tests/                      # Automated regression & browser interaction test suite
├── templates/                      # HTML editor, UI designs, and subtitle presets
│   ├── editor.html                 # Offline batch subtitle & preview editor
│   └── catalog.json                # Approved subtitle styles catalog
├── template-gallery/               # Subtitle animation style gallery & Swift renderer
├── .env.example                    # Safe environment template (Zero secrets)
├── .gitignore                      # Multi-layer privacy & security firewall
└── README.md                       # Comprehensive workflow documentation
```

---

## Security & Privacy Firewall / 隱私安全防護原則

This repository strictly separates **public source code** from **private media and credentials**:

1. **Source Code is Public; Media & Secrets are Strictly Private**:
   * All raw videos (`.mp4`, `.mov`), audio tracks (`.mp3`, `.wav`), personal photos (`.jpg`, `.png`), and subtitles (`.srt`) are strictly excluded from Git tracking via multi-layer `.gitignore`.
2. **Zero Credentials in Git**:
   * API keys, tokens, and secrets must only live in local `.env` files. Templates (`.env.example`) provide placeholder variable names only.
3. **Local Loopback Security**:
   * The local controller binds exclusively to `127.0.0.1` using per-launch randomized session tokens and same-site cookies, preventing foreign origin access.
4. **Mandatory Pre-Commit Checks**:
   * Always verify `git status` and `git diff --cached` before committing to ensure no private media or secrets are staged.

---

## Subtitle Styling Specs / 字幕排版規範

* **Character Limits (字數上限)**:
  * Vertical (9:16) / Square: Max 10 Chinese characters per line.
  * Horizontal (16:9): Max 16 Chinese characters per line.
  * Maximum 2 lines per cue; overflow smoothly breaks into the next monotonic cue.
* **Bilingual Ratio (雙語字級)**:
  * Chinese font scale: 100% (bold white with high-contrast black outline, S02 standard).
  * English font scale: 70% default (adjustable from 40% to 90%).
