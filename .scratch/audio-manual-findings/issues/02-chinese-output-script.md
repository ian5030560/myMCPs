# 02: 繁體中文錄音轉出簡體字，且有辨識錯誤

**Status:** resolved

**Found by:** audio#11（`language`）與 audio#20（中文接字），2026-11-07 實測。

## 觀察

素材是 Common Voice zh-TW 的六句（繁體逐字稿、台灣口音）。`gemini/gemini-3.5-transcribe`：

- `language="zh"`：輸出全是簡體字（「两国总统都没有直接通过电话」），也沒有分行。
- 沒給 `language`、`timestamps=true`：同樣是簡體；第一句「臺北市政府警察局中山分局」變成「新北市政府警察局中山分局」，第四句「她走到客廳」變成「他走到客廳」。

中文字之間沒有空格，分行與時間（0、7、13、21、28、33 秒）正確，所以 #20 的接字部分是好的，失敗的是「與腳本相符」。

## 待決定

- 這是模型的行為還是工具可以影響的（`language` 的值是否能用 `zh-TW`／`zh-Hant`，或在提示詞要求繁體）。
- 工具是否要對繁體使用者提供一個參數，或只在文件說明。
- 「新北／臺北」「她／他」是模型辨識錯誤，不一定是工具問題；若決定不處理，改寫 audio#20 的預期。

## 調查（2026-11-15）

素材同 audio#20（Common Voice zh-TW 六句，37.5 秒），`gemini/gemini-3.5-transcribe`，工具的 `Transcriber` 直接呼叫，各組合跑 1 到 2 次：

| `language` | 不要時間 | `timestamps=true` |
|---|---|---|
| 不給 | 簡體 | 簡體 |
| `zh` | 簡體 | 簡體 |
| `zh-TW` | **繁體**（臺北市…、兩國總統…） | 簡體 |
| `zh-Hant`、`zh-Hant-TW`、`cmn-Hant-TW` | **繁體** | 簡體 |

- `language="zh"` 簡體的原因：LiteLLM 把裸的 `zh` 轉成 BCP-47 的 `zh-CN`（`litellm_core_utils/audio_utils/utils.py` 的 `BARE_ISO_639_1_TO_BCP47`）才送出 `language_codes`，所以是照要求給簡體。含 `-` 的代碼（`zh-TW`、`zh-Hant`）則原樣送出。
- 開著 `timestamps` 時，LiteLLM 送出的請求同時帶 `language_codes` 與 `mode: {type: "verbatim", timestamp_granularities: ["word"]}`；在這個模式下，不論 `language` 是什麼，輸出都是簡體。這是供應商端的行為，工具與 LiteLLM 都沒有可以調的參數。
- 辨識錯誤是模型的雜訊，不是工具的：「新北」這次沒有再出現（變成「台北」，與「臺北」只是字形差異）；「她／他」在不同次的呼叫之間會變（同一個設定有時對、有時錯）。

## 決定

- 不加參數、不在工具裡轉換字形（OpenCC 之類的轉換是新的相依套件，且只能補一部分）。
- 在工具說明（`transcribe_audio` 的 `language`）與 README 寫清楚：裸的 `zh` 是簡體；要繁體用 `zh-TW` 或 `zh-Hant`；開著 `timestamps` 時 Gemini 一律寫簡體。
- audio#11 的預期改為簡體；#20 的預期改為只看接字、分行與時間，字形與偶爾的同音字錯誤都算通過；新增 #34 驗證 `zh-TW` 不開 `timestamps` 時是繁體。

## 沒驗證的

- OpenAI 的 `whisper-1` 等模型對 `zh` 的字形（沒有 OpenAI 金鑰）。常見的做法是在提示詞寫繁體字的句子，但工具目前沒有提示詞參數，沒有測。
- 同時要繁體與時間：目前沒有辦法。若之後有需要，可考慮先用不開 `timestamps` 的結果取字、再用開 `timestamps` 的結果取時間，但兩份文字要對齊，這次沒做。
