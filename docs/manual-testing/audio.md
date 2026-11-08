# 音訊伺服器實測清單

`mymcps-audio` 的 mock 測試無法證明它能和真實供應商一起運作，這份清單列出需要手動驗證的檢查。操作方式見 [README.md](README.md)；撰寫規則見 [docs/agents/manual-testing.md](../agents/manual-testing.md)。

項目的結果不寫在這裡，每次執行另外記錄在 `runs/`。引用項目時寫 `audio#N` 並附簡短描述。

## 設定檔範本

最小設定（Gemini）：

```toml
[audio]
listen_model     = "gemini/gemini-3.8-flash"
transcribe_model = "gemini/gemini-3.5-transcribe"
```

測 OpenAI 時，呼叫時傳 `model="openai/whisper-1"`（或 `openai/gpt-4o-transcribe`），不必改設定檔。模型名稱以當時 LiteLLM 的模型表與帳號權限為準。

## 測試素材

### `assets/speech-en.mp3`

約 42 秒的英文朗讀（[assets/speech-en.mp3](assets/speech-en.mp3)，64 kbps、單聲道）：取自 LJ Speech 1.1（Keith Ito 與 Linda Johnson，公有領域）的六段，段與段之間插入 1.5 秒的靜音。工具的路徑參數請給它的絕對路徑。

| 句 | 片段 | 檔案中的起點 | 預期的 `[hh:mm:ss]`（誤差 ±1 秒） | 內容 |
|---|---|---|---|---|
| 1 | LJ004-0028 | 0.00 秒 | 00:00:00 | Various acts were also passed to consolidate and amend previous jail acts. |
| 2 | LJ004-0057 | 6.66 秒 | 00:00:07 | For the first time the doctrine was enunciated that prisoners had rights of their own. |
| 3 | LJ005-0095 | 13.28 秒 | 00:00:13 | The promulgation of these two Jail Acts strengthened the hands of the Prison Discipline Society enormously. |
| 4 | LJ005-0106 | 21.50 秒 | 00:00:22 | Jails, of which the old prison at Reading was a specimen, were still left intact. |
| 5 | LJ006-0047 | 28.45 秒 | 00:00:28 | The prison had become more or less a place of detention only, harboring mainly those awaiting trial. |
| 6 | LJ004-0216 | 35.55 秒 | 00:00:36 | The most noticeable of the improvements introduced was a better regulation of dietaries within the prison. |

逐字稿與腳本的差異只應該是大小寫與標點，或極少數字詞。

### 中文錄音（不提交，每次現做）

需要中文的項目（#11、#20）用 Common Voice 27.0 的繁體中文（zh-TW）做。它的資料集頁面註明「禁止重新託管或再分享」，所以**音檔不進 repo**，下面只記錄怎麼取得與預期內容。`mp3` 檔名前綴是 `common_voice_zh-TW_`，編號固定在 `cv-corpus-27.0-2026-09-11` 這一版。

前置：到 [資料集頁面](https://mozilladatacollective.com/datasets/cmu5wkw5i00c6o107jnm3t51u) 登入、同意條款，在個人設定建立 API 金鑰並放進環境變數 `MDC_API_KEY`（條款只能在網頁同意，API 不支援；每個機構每天預設 7 次下載額度）。

```bash
URL=$(curl -s -X POST -H "Authorization: Bearer $MDC_API_KEY" -H "Content-Type: application/json" -d '{}' \
  https://mozilladatacollective.com/api/datasets/cmu5wkw5i00c6o107jnm3t51u/download | python -c "import json,sys;print(json.load(sys.stdin)['downloadUrl'])")
curl -r 0-33554431 -o head.tar.gz "$URL"
gzip -dc head.tar.gz | tar -x --wildcards '*/validated.tsv' '*/clip_durations.tsv' '*/clips/*'
```

- 完整壓縮檔約 3.2 GB，儲存空間支援範圍請求，只取開頭 32 MB 就有約 900 段 mp3；壓縮檔裡 tsv 排在 `clips/` 之前。`tar` 最後會印 `Unexpected EOF`，預期內。
- 預簽網址不要寫進檔案或貼出來，它是有時效的憑證。
- 把下面六段依序接起來，段間插入 1.5 秒靜音，轉成單聲道 64 kbps mp3，約 37 秒。每段開頭本來就有 0 到 1 秒的留白，所以起點誤差放寬到 ±2 秒。

| 句 | 檔名編號 | 檔案中說話開始約 | 預期的 `[hh:mm:ss]`（±2 秒） | 內容 |
|---|---|---|---|---|
| 1 | 17370004 | 0.1 秒 | 00:00:00 | 臺北市政府警察局中山分局 |
| 2 | 17369547 | 6.5 秒 | 00:00:07 | 兩國總統都沒有直接通過電話 |
| 3 | 17371815 | 13.4 秒 | 00:00:13 | 運用數位工具及知識平台打造獨特產品 |
| 4 | 17373382 | 20.2 秒 | 00:00:20 | 當功課都做完後，她走到客廳 |
| 5 | 17370151 | 27.6 秒 | 00:00:28 | 致力於提升女性勞動參與率 |
| 6 | 17370175 | 33.3 秒 | 00:00:33 | 平時會僱用工人照顧田地 |

逐字稿與腳本的差異只應該是標點與異體字（例如「臺」與「台」）。這份素材沒有英文單字；中英混排的接字另請自備一小段錄音。

### 長錄音（不提交，每次現做）

分 chunk 與 Files API 的項目需要超過 Gemini 單次上限的錄音：轉錄超過 1 小時（要時間則超過 30 分鐘）會分 chunk，聆聽超過 20 MB（壓縮成 32 kbps 後約 83 分鐘）走 Files API，所以做約 90 分鐘的就兩者都涵蓋。做法是取 LJ Speech 壓縮檔開頭的幾段，接成約 90 分鐘（內容不重複，也有現成的標準逐字稿）。在一個新的空資料夾裡執行（`ffmpeg` 用 `.venv` 裡 `imageio_ffmpeg` 附的那一個）：

```bash
curl -r 0-175000000 -o head.tar.bz2 https://data.keithito.com/data/speech/LJSpeech-1.1.tar.bz2
bzip2 -dc head.tar.bz2 | tar -x --wildcards 'LJSpeech-1.1/wavs/*' 'LJSpeech-1.1/metadata.csv'
ls LJSpeech-1.1/wavs/*.wav | sed "s/.*/file '&'/" > list.txt
ffmpeg -f concat -safe 0 -i list.txt -ac 1 -b:a 64k long.mp3
```

- `tar` 最後會印出 `Unexpected EOF`，這是預期的（壓縮檔被截斷）；最後一段 wav 可能不完整，`ffmpeg` 會照現有的讀。
- 約 175 MB 的下載可得約 90 分鐘。下載量與長度大致成正比：75 MB 約得 39 分鐘。
- 預期逐字稿：`metadata.csv` 中，檔名有出現在 `list.txt` 的那些列，依檔名排序，第二欄就是每段的文字。
- 段與段之間沒有人為的靜音，只有各段自己的前後留白。

只需要「很長但不在乎內容」的檔案時（#24、#25、#33），用 `ffmpeg -f lavfi -i anullsrc=r=16000:cl=mono -t <秒數> -b:a <位元率> silence.mp3` 產生靜音檔即可。

## 清單

### 啟動與 `list_models`

| ID | 檢查 | 步驟／輸入 | 預期 | 需求 |
|---|---|---|---|---|
| #1 | 啟動 | 用範本設定檔啟動伺服器，看 stderr 與 stdout | stderr 列出載入的檔案；stdout 沒有雜訊；不出現 Traceback | 無 |
| #2 | 工具清單 | `tools/list` | 有 `list_models`、`transcribe_audio`、`listen_audio` | 無 |
| #3 | `list_models` | 呼叫 `list_models` | 兩個用途（`listen`、`transcribe`）顯示設定的模型；沒有金鑰或端點 | 無 |
| #4 | 沒有金鑰 | 不設任何金鑰，用 `speech-en.mp3` 呼叫 `transcribe_audio` 與 `listen_audio` | 各是可讀的一行錯誤，指出要設哪個環境變數，沒有 Traceback | 無 |
| #5 | 用途沒設定模型 | 設定檔不寫 `transcribe_model`（再試 `listen_model`），呼叫對應的工具 | 錯誤訊息指出該欄位與 `[audio]` 區段 | 無 |
| #6 | 壞輸入在呼叫模型之前被拒絕 | 不設金鑰，依序給：不存在的路徑、內容是文字的 `.mp3`、沒有音軌的影片 | 各是可讀的輸入錯誤（不是缺金鑰），代表在呼叫模型之前就失敗 | 無 |
| #7 | 時間範圍不合理 | 對 `speech-en.mp3` 給 `start=60`、`start=20 end=10`、`start=abc` | 各是可讀的錯誤，不是 Traceback | 無 |
| #8 | 模型不收音訊 | `transcribe_audio` 的 `model` 給 `openai/gpt-3.5-turbo`；`listen_audio` 同樣給它 | 錯誤指出該模型不能做這件事與該設哪個欄位，沒有呼叫模型 | 無 |

### `transcribe_audio`

| ID | 檢查 | 步驟／輸入 | 預期 | 需求 |
|---|---|---|---|---|
| #9 | OpenAI 接受壓縮格式 | `model="openai/whisper-1"`，`speech-en.mp3` | 成功；逐字稿與腳本只差大小寫與標點，或極少數字詞 | `OPENAI_API_KEY`、會計費 |
| #10 | Gemini 接受壓縮格式 | `model="gemini/gemini-3.5-transcribe"`，`speech-en.mp3` | 成功；逐字稿與腳本只差大小寫與標點，或極少數字詞 | `GEMINI_API_KEY`、會計費 |
| #11 | `language` | 上面做好的中文錄音，`language="zh"` | 輸出是中文，沒有被當成別的語言 | `GEMINI_API_KEY`、會計費 |
| #12 | `start`／`end` | `speech-en.mp3`，`start=13 end=22 timestamps=true`，用 `openai/whisper-1` | 只轉出第 3、4 句；第一行時間約 `00:00:13`（從原檔起算，不是 `00:00:00`） | `OPENAI_API_KEY`、會計費 |
| #13 | URL 輸入 | `path` 給 repo 在 raw.githubusercontent.com 上的 `speech-en.mp3` 網址 | 成功；系統暫存資料夾裡找不到 `mymcps-dl-*` | `OPENAI_API_KEY`、會計費 |
| #14 | 模型沒有時間 | `model="openai/gpt-4o-transcribe"`，`timestamps=true` | 錯誤指出該模型沒有時間，並建議改用能回傳時間的模型 | `OPENAI_API_KEY`、會計費 |
| #15 | 暫存檔清除 | 做完 #4（失敗）與 #9（成功）後，看系統暫存資料夾的 `mymcps/work` | 裡面沒有殘留的檔案 | 無 |

### 時間戳與逐字分行

| ID | 檢查 | 步驟／輸入 | 預期 | 需求 |
|---|---|---|---|---|
| #16 | `whisper-1` 的句子時間 | `model="openai/whisper-1"`，`speech-en.mp3`，`timestamps=true` | 每行有 `[hh:mm:ss]`；各行起點與上表相差在 1 秒內（人工對照） | `OPENAI_API_KEY`、會計費 |
| #17 | Gemini 逐字時間確實回來 | `model="gemini/gemini-3.5-transcribe"`，`timestamps=true` | 有時間，沒有出現「returns no timestamps」 | `GEMINI_API_KEY`、會計費 |
| #18 | Gemini 逐字欄位的格式 | 同 #17，檢視輸出 | 英文行的字之間恰有一個空格，沒有黏在一起或雙空格，標點位置合理；記錄 `word` 是否已含空格或標點 | `GEMINI_API_KEY`、會計費 |
| #19 | 停頓與 10 秒上限分行 | 同 #17 | 六句各自一行（句間 1.5 秒的靜音大於 0.8 秒的門檻），行首時間與上表相差在 1 秒內，沒有超過 10 秒的行 | `GEMINI_API_KEY`、會計費 |
| #20 | 中文接字 | 上面做好的中文錄音，`model="gemini/gemini-3.5-transcribe"`，`timestamps=true` | 中文字之間沒有空格；與六句腳本相符（標點與異體字除外） | `GEMINI_API_KEY`、會計費 |

### 長錄音分 chunk

這幾項需要超過上限的錄音。Gemini 轉錄模型的上限是每個請求 1 小時，要時間（`timestamps`）時是 30 分鐘；OpenAI 是 25 MB（壓縮後約 104 分鐘）。每個 chunk 目標是上限的 9 成、最長 95%，所以 90 分鐘的錄音不要時間會分 2 個 chunk，要時間會分 4 個。Gemini 免費或 Tier 1 帳號每分鐘只能送 1 萬個輸入 token，連續送 chunk 會遇到限流，工具會等待後重送，所以這幾項在低層級帳號上要跑很久（記錄實際花了多久）。

| ID | 檢查 | 步驟／輸入 | 預期 | 需求 |
|---|---|---|---|---|
| #21 | 超過上限會分 chunk | 約 90 分鐘的 `long.mp3`，`model="gemini/gemini-3.5-transcribe"` | 成功；逐字稿涵蓋全長，最後一句與標準逐字稿的最後一句相符；供應商的用量顯示 2 次轉錄請求 | `GEMINI_API_KEY`、會計費 |
| #22 | 切點落在停頓處 | 同 #21，看第一次切點附近（約第 51 到 57 分鐘）的逐字稿，對照標準逐字稿 | 沒有句子被切成兩半、沒有掉字或重複 | `GEMINI_API_KEY`、會計費 |
| #23 | 時間跨 chunk 正確 | 同 #21，加 `timestamps=true`（會分 4 個 chunk）；在第二個 chunk（約 26 分鐘之後）抽查三行，用 `ffmpeg -ss <時間> -t 8` 切出原檔該處聽 | 內容與該行相符，偏差在 1 秒內 | `GEMINI_API_KEY`、會計費 |
| #24 | 被拒絕的 chunk 有標記 | 起假的本機服務（第一個請求回 `{"text":"ok"}`，第二個回 400），`[providers.openai]` 的 `api_base` 指向它；110 分鐘的靜音檔（`-t 6600 -b:a 32k`），`model="openai/whisper-1"` | 結果中出現 `[not transcribed 時間-時間: ...]`，其他 chunk 的文字還在，工具沒有失敗 | 無 |
| #25 | 中途限流 | 同 #24，但第二個請求之後都回 429（`Retry-After` 給 1 秒以免等太久） | 工具不失敗；第一個 chunk 的文字還在，限流的 chunk 與之後的 chunk 各有 `[not transcribed ...]`；中間有等待（每次約 2 秒），伺服器共收到 1 + 18 次請求（工具試 6 次，LiteLLM 每次自己再送 3 次） | 無 |

### `listen_audio`

| ID | 檢查 | 步驟／輸入 | 預期 | 需求 |
|---|---|---|---|---|
| #26 | 基本詢問 | `speech-en.mp3`，`prompt="What is this recording about? Answer in one sentence."` | 答案與內容相符（談監獄與監獄法案） | `GEMINI_API_KEY`、會計費 |
| #27 | 模型照 `[hh:mm:ss]` 格式 | `timestamps=true`，`prompt="When does each sentence start?"` | 答案裡有 `[hh:mm:ss]`，沒有出現「gave no timestamps」 | `GEMINI_API_KEY`、會計費 |
| #28 | 時間從這段音訊的 0 秒算起 | `start=13 timestamps=true`，`prompt="When does the first sentence start?"` | 答案的時間約 `[00:00:13]`（誤差 2 秒內）；若約 `[00:00:26]`，代表模型沒有從 0 算起，記錄實際行為並開票 | `GEMINI_API_KEY`、會計費 |

### 大檔聆聽（Files API）

下面 #29 到 #32 用同一次呼叫的 `long.mp3`（約 90 分鐘，壓縮後超過 Gemini 的 20 MB 內嵌上限）。這幾項最可能讓現有實作需要修改，建議先跑。

| ID | 檢查 | 步驟／輸入 | 預期 | 需求 |
|---|---|---|---|---|
| #29 | 上傳後檔案是否已就緒 | `long.mp3`，`listen_model` 用 Gemini，`prompt="Summarize in one sentence."` | 成功回答；沒有出現檔案尚未就緒（`PROCESSING`、不是 `ACTIVE`）一類的錯誤。若出現，開票補輪詢檔案狀態 | `GEMINI_API_KEY`、會計費 |
| #30 | 檔案參照的 `format` 被接受 | 同 #29 | 沒有出現 `format` 或 MIME 被拒絕的錯誤；若被拒絕，記錄錯誤文字並開票 | `GEMINI_API_KEY`、會計費 |
| #31 | 回答後上傳的檔案被刪除 | 做完 #29，到 Google AI Studio 的檔案列表，或用金鑰呼叫 Gemini 的檔案列表 API | 剛上傳的檔案不在列表中 | `GEMINI_API_KEY` |
| #32 | 詢問失敗時也刪除 | `model="gemini/does-not-exist"`，`long.mp3` | 工具回傳模型不存在的錯誤；上傳的檔案仍已被刪除（同 #31 的查法） | `GEMINI_API_KEY`、會計費 |
| #33 | 超過 9.5 小時的上限 | 產生約 9.6 小時的靜音檔（`ffmpeg -f lavfi -i anullsrc=r=16000:cl=mono -t 34560 -b:a 8k long-silence.mp3`），呼叫 `listen_audio` | 在上傳前就報錯，訊息說明兩條路（用 `start`／`end` 依序處理並把筆記帶進下一次的 `prompt`，或先 `transcribe_audio`）；沒有任何上傳 | 無 |

## 建議的執行順序

1. 不需要金鑰：#1～#8、#15、#33，再用假服務跑 #24、#25。
2. Gemini 金鑰，先用短素材：#10、#17～#19、#26～#28。
3. Gemini 金鑰，再跑長錄音（最貴）：先 #29～#32（找出需要補票的問題），再 #21～#23。
4. OpenAI 金鑰：#9、#12、#13、#14、#16。
5. 中文錄音做好後（需要 `MDC_API_KEY`）：#11、#20。

長錄音的項目會花最多錢，第一次只做最短能觸發分 chunk 或 Files API 的長度（約 85 分鐘），不要用數小時的檔案。

## 這份清單不能證明的事

- 各供應商的模型名稱與帳號權限（只能看到實際回應）。
- 素材是棚內錄音的單一講者英文；多講者、雜訊、音樂、其他語言的辨識品質，以及 `listen_audio` 對語氣與環境聲的判斷，都沒有涵蓋。
- 32 kbps 壓縮對品質的影響只能用乾淨的語音觀察，雜訊多的錄音可能更差。
- 限流與供應商拒絕只能用假服務模擬，真實錯誤的文字可能不同。
- macOS 行為。
