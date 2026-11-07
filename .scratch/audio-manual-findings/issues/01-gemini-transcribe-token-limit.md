# 01: Gemini 轉錄模型的單次上限是時間，不是 20 MB

**Status:** resolved

**Found by:** audio#21（長錄音超過上限會分 chunk）與 audio#22，2026-11-07 實測。

## 觀察

用 `gemini/gemini-3.5-transcribe` 轉錄約 91 分鐘的錄音（壓縮後 21.9 MB，超過 `limits.py` 的 20 MB，所以被分成兩個 chunk：0 到 71 分 17 秒、71 分 17 秒到結尾）。第一個 chunk 被供應商拒絕：

```
litellm.ContextWindowExceededError: ... GeminiException -
{"error":{"message":"The input token count exceeds the maximum number of tokens allowed 98304.","code":"invalid_request"}}
```

第二個 chunk（約 20 分鐘）成功，145 行的時間都與原檔相差在 1 秒內。結果是一份缺了前 71 分鐘、只在開頭有 `[not transcribed 00:00:00-01:11:17: ...]` 標記的逐字稿，工具沒有失敗。

## 原因

`limits.py` 只用位元組數（20 MB，約 83 分鐘）決定每個 chunk 的最長長度，但這個模型有時間上限。模型文件寫：每個請求最長 1 小時，要說話者分離或字詞時間（工具的 `timestamps` 就是字詞時間）時最長 30 分鐘。實測：

- 71 分鐘的 chunk：超過 98,304 個輸入 token（音訊每秒 25 個 token）被拒絕。
- 約 48 分鐘、要字詞時間：回 `status=incomplete`，LiteLLM 因此丟出錯誤。
- 約 28 分鐘（1700 秒）、要字詞時間：成功，244 行，時間與原檔相差在 0.55 秒內。

## 修正

- `limits.py`：Gemini 加 `transcribe_seconds`（3600）與 `timed_transcribe_seconds`（1800）；位元組上限保留。
- `transcriber.py`：要 `timestamps` 時用較短的時間上限；一個請求是否需要分 chunk、每個 chunk 最長多長，取位元組與時間兩者較嚴的。
- 測試：時間上限會分 chunk、沒超過不分、要 `timestamps` 用較短的上限、鎖住 Gemini 數值。
- 文件：README、CLAUDE.md、`audio.md`（#21～#23 的 chunk 數與切點位置）。

## 沒有解決的部分

- 完整 91 分鐘的分 chunk 流程在真實 API 上還沒跑完，因為 Tier 1 帳號每分鐘只能送 1 萬個輸入 token，第二個 chunk 被限流，見 [04](04-chunk-rate-limit.md)。audio#21、#22 要等那邊處理或換較高層級的帳號後重跑。
- 被拒絕的 chunk 在第一個位置時，整份結果看起來「成功」（`is_error: False`）。是否要在大部分內容都沒有轉出來時改成失敗，另外決定。
