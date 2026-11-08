# 04: 分 chunk 時連續送請求會撞到每分鐘 token 限流

**Status:** resolved

**Found by:** 修 [01](01-gemini-transcribe-token-limit.md) 後重跑 audio#21，2026-11-07 至 08。

## 觀察

91 分鐘的錄音、`timestamps=true`，分成每個約 26 分鐘（約 3.8 萬個輸入 token）的 chunk。第一個 chunk 送出後，下一個被限流：

```
Rate limit exceeded for model gemini-3.5-transcribe (limit: 10000 input tokens per minute on Tier 1).
Please retry in 51s ...
```

原本的設計（限流就中止）讓整個工具失敗，已轉好的第一個 chunk 的結果也一起遺失（audio#25 已記錄過）。

## 決定（使用者，2026-11-08）

等待後重送，用盡再回傳已完成的部分。

## 修正

- `RateLimitError.retry_after`：`core/llm.py` 從 `Retry-After` 標頭，或訊息裡的「retry in 51s」解析供應商要求的等待。
- `Transcriber._send`：限流時等待（供應商要求的秒數，上限 120 秒，再加 1 秒；沒有提示時 30 秒）後重送同一個 chunk，最多重送 5 次。
- 仍被限流：該 chunk 標成 `[not transcribed ...: 原因]`，之後的 chunk 標成 `[not transcribed ...: not sent after the rate limit above]` 且不再送出，已完成的文字照常回傳。第一個 chunk 就失敗（沒有任何完成）或只有單一請求時仍是錯誤。
- 這改變了「auth、model-not-found、rate-limit 錯誤中止」的決定：現在只有前兩種中止。

## 驗證

- 單元測試：等待後重送、無提示用預設、等待上限、用盡後的標記、一開始就限流、單一請求，以及等待時間的解析（標頭優先於文字）。
- 真實 API（Gemini Tier 1）：91 分鐘、`timestamps=true`，分 4 個 chunk，共等待 6 次（11 到 58 秒），7 分鐘跑完。787 行，沒有 `[not transcribed]` 標記，時間與原檔相差 -0.85 到 +0.59 秒，涵蓋所有 chunk 接縫。
- 假服務（audio#25）：第二個 chunk 持續 429 時，工具不失敗，回傳第一個 chunk 的文字加標記。

## 要知道的取捨

- 低層級帳號上，一次呼叫可能等好幾分鐘（上面是 7 分鐘）。若呼叫端（MCP 客戶端）有逾時，可能在工具回來前先放棄；等待過程只寫在 stderr 的警告，沒有進度回報給呼叫者。
