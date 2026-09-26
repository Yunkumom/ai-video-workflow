# AI Video Workflow v7

A macOS-native subtitle-first program with one owner-facing flow: `1 Input → 2 Process → 3 Output`.
這是一個字幕優先的 macOS 本機程式，擁有者只需要操作 `1 Input → 2 Process → 3 Output`。

## GUI onboarding / GUI 入門

`templates/editor.html` v2 includes Setup → Input → AI Analysis → Output guidance and the bilingual “Editor 編輯器” title. The checklist is manual; AI processing requires the local controller.

`templates/editor.html` v2 已整合環境設定、素材資料夾、AI 分析與輸出指南，名稱採用「Editor 編輯器」。環境清單為手動確認；AI 處理仍需本機控制器。

## Open / 開啟

1. Open `templates/editor.html` directly for the basic offline preview: select a video folder, load matching SRT or paste per-video transcripts, and review every cue against the picture.
2. Double-click `AI Video Workflow v7.command` for the current desktop editor: create or open a project, then import media, edit, and generate output locally.

1. 直接開啟 `templates/editor.html` 使用陽春離線預覽：選擇影片資料夾、配對 SRT 或逐片貼上逐字稿、切句，並對照畫面逐句檢查。
2. 雙擊 `AI Video Workflow v7.command` 使用目前的桌面編輯器：建立或開啟專案後，在本機匯入素材、編輯並生成輸出。

中間的辨識與渲染資料保存在 `2_processing/`；擁有者仍只需使用 `1_input → 2_processing → 3_output` 三個區塊。

## 第一輪試用修正

- 中央「＋」和右上角載入按鈕使用同一個資料夾選擇器。
- Input 支援影片與 **JPG／JPEG／PNG 照片**混合排序；其他照片格式（含 HEIC）會提示略過，需先轉成 JPG／PNG，不會擅自轉檔或改原檔。
- 每列「×」只從本次清單移除；「復原移除」保留最近一次移除項目的字幕、註解、順序及既有成果連結，不刪原檔或已匯入的工作副本。
- Process 的「＋ 新增字幕」可從零加入文字與時間，也能補入空白時段；重疊或超出素材時間時拒絕套用，超長文字依既有字數限制切句。
- 照片預設沿用 5 秒，可調 0.1～3600 秒並按「套用秒數」，有字幕時不能縮短到字幕結束之前。照片不送語音辨識；可輸出有字幕或無字幕的靜態 MP4（無音軌），不合併素材。奇數尺寸只在右／下補最多 1 像素供 H.264 編碼，不裁切。
- 缺少 `GROQ_API_KEY` 時，會在批次匯入／辨識前顯示設定提示，不建立整批失敗工作。這只是前置檢查，**不等於已設定金鑰或驗證外部辨識服務**。程式不讀取 `.env` 或其他憑證檔；仍須擁有者設定啟動環境並重新啟動。

重試新版前請先保存私人工作檔，停止原先啟動程式的終端工作，再重新雙擊啟動器；只重新整理網頁不會更新仍在執行的 Python 控制器。若拿已處理 V1 試用，請連同**同名 SRT**載入；燒在畫面上的字幕不會自動變成可編輯字幕。

新的私人工作檔使用 `shine.subtitle-workspace.v2`，額外保存素材類型及照片秒數，也可還原舊 v1。若移除部分素材後保存，重新選取原資料夾並載入工作檔時，只還原保存的清單，不會把已移除項目自動加回。來源檔案依舊不會被刪除。

## Compact batch workbench / 緊湊批次工作台（2026-08-30）

- **Input**：載入整個影片資料夾（包含子資料夾），或選多支影片；先依檔名自然排序，再用上下箭頭調整。每頁 6 支，同名 SRT 只與同一路徑的影片配對，隱藏檔案會略過。
- **Process**：一次校對一支影片，切換影片、閱讀段落與字幕頁；每句都有開始／結束時間及註解。「分段／重切」可指定完整範圍、句數和段數；只分段保留時間，重切則依字數估算，仍須對照影片確認。
- **Output**：逐支輸出 MP4／SRT，保留原長度、方向與原聲，不自動剪掉停頓、裁切或合併。這是字幕工作台輸出，不取代既有 Vlog／Reel 雙格式製作規格。
- **☰ 選單**：開啟 GUI Guide，或保存／還原私人工作檔。Template 在 Process「樣式」彈窗中，Mature／Testing 分頁不另建資料夾。

私人工作檔 `*.subtitle-workspace.json` 包含相對檔名、排序、字幕、註解、未套用逐字稿與樣式 ID，不包含影片、絕對路徑或 API 金鑰。下次先選取相同資料夾再載入工作檔；檔案大小及修改時間必須符合，這不是內容雜湊驗證。工作檔限 8 MB、只手動保存，並由 Git 忽略；不要分享或提交。匯入舊工作後會標記既有成片需要重輸出。

完整語音辨識依序處理每支影片全部音訊，長片每 10 分鐘一段，顯示進度並還原全片時間碼；任一段失敗不交付部分辨識結果。一次最多載入 1000 支影片；影片最長 48 小時，每片最多 10000 個字幕 cue。個別失敗不影響後續影片；「停止後續影片」會先完成目前這支。

AI 排序目前只根據檔名，不分析影像內容，單次限 200 支；AI 修正只傳送本片有註解的文字，每批 40 句。兩者均使用既有 Groq，需逐次勾選同意且啟動環境已有 `GROQ_API_KEY`，提案確認後才套用，可復原。這次驗證使用模擬 AI 回覆，未呼叫真實外部服務。

離線版無需外部連線，可選資料夾、預覽、校對與匯出 SRT；MP4 渲染／完整語音辨識／AI 提案需增強版。瀏覽器須能預覽影片編碼；無法讀取的格式可先用增強版辨識取得資訊，或轉為 H.264 MP4。S01 保留貼字黑底；S03～S05 正式成片仍為靜態基礎，未新增動態效果。

官方服務參考：[Groq 語音辨識](https://console.groq.com/docs/speech-to-text)、[文字處理](https://console.groq.com/docs/text-chat)。

## Subtitle limits / 字幕限制

- Portrait or square: at most 10 Chinese characters per line.
- Landscape: at most 16 Chinese characters per line.
- At most two lines; overflow becomes the next timed cue.
- S01 black backgrounds fit each rendered line instead of creating one large band.

- 直式或方形：每行最多 10 個中文字。
- 橫式：每行最多 16 個中文字。
- 最多兩行，溢出內容會成為下一個有時間碼的 cue。
- S01 黑底只貼合每一行實際文字，不再形成大片黑帶。

## Privacy / 隱私

The standalone program never uploads media; enhanced mode binds only to `127.0.0.1`. External transcription remains off unless the owner explicitly approves that exact video, and credentials are never read from `.env`, stored, displayed, or logged.

陽春版不會上傳媒體；增強版只綁定 `127.0.0.1`。除非擁有者針對該支影片明確同意，否則外部轉錄維持關閉，憑證不得從 `.env` 讀取、保存、顯示或記錄。
