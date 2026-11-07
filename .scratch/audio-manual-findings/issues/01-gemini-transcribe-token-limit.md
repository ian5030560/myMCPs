# 01: Gemini 轉錄模型的單次上限是 token，不是 20 MB

**Status:** needs-triage

**Found by:** audio#21（長錄音超過上限會分 chunk）與 audio#22，2026-11-07 實測。

## 觀察

用 `gemini/gemini-3.5-transcribe` 轉錄約 91 分鐘的錄音（壓縮後 21.9 MB，超過 `limits.py` 的 20 MB，所以被分成兩個 chunk：0 到 71 分 17 秒、71 分 17 秒到結尾）。第一個 chunk 被供應商拒絕：

```
litellm.ContextWindowExceededError: ... GeminiException -
{"error":{"message":"The input token count exceeds the maximum number of tokens allowed 98304.","code":"invalid_request"}}
```

第二個 chunk（約 20 分鐘）成功，145 行的時間都與原檔相差在 1 秒內。結果是一份缺了前 71 分鐘、只在開頭有 `[not transcribed 00:00:00-01:11:17: ...]` 標記的逐字稿，工具沒有失敗。

## 原因（推測，未驗證）

這個模型的限制是每個請求 98,304 個輸入 token。若音訊約 32 token／秒，上限約 51 分鐘；`limits.py` 目前只用位元組數（20 MB，約 83 分鐘）決定要不要分 chunk，也決定每個 chunk 的目標長度，所以 chunk 會超過 token 上限。

## 待決定

- 轉錄的 chunk 長度是否要加一個依時間（或 token）的上限，放進 `limits.py` 的每廠商限制表。
- 實際的 token／秒要實測決定，不要用推測。
- 修好後，audio#21、#22 才能重跑（目前 #22 因此無法判斷第一個切點）。

另外觀察到：被拒絕的 chunk 在第一個位置時，整份結果看起來「成功」（`is_error: False`）。是否要在大部分內容都沒有轉出來時改成失敗，也一併決定。
