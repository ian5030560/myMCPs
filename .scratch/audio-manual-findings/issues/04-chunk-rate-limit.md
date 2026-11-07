# 04: 分 chunk 時連續送請求會撞到每分鐘 token 限流

**Status:** needs-triage

**Found by:** 修 [01](01-gemini-transcribe-token-limit.md) 後重跑 audio#21，2026-11-07 至 08。

## 觀察

91 分鐘的錄音、`timestamps=true`，分成每個約 26 分鐘（約 3.8 萬個輸入 token）的 chunk。第一個 chunk 送出後，下一個被限流：

```
Rate limit exceeded for model gemini-3.5-transcribe (limit: 10000 input tokens per minute on Tier 1).
Please retry in 51s ...
```

依目前的設計（限流就中止），整個工具失敗，已轉好的第一個 chunk 的結果也一起遺失（audio#25 已記錄過這個行為）。重試兩次都在第二個 chunk 失敗。

## 影響

在 Tier 1 帳號上，Gemini 的長錄音轉錄（超過 1 小時，或要時間且超過 30 分鐘）實際上跑不完。較高層級的帳號未驗證。

## 待決定

- 遇到限流時，是否依回應裡的等待時間（`Retry-After` 或訊息裡的秒數）等待後重送同一個 chunk，等待總時間要不要設上限。
- 或維持中止，但把已完成的 chunk 結果隨錯誤一起回傳，讓呼叫者用 `start`／`end` 接著做。
- 這會改變 ADR 0005 與規格「auth、model-not-found、rate-limit 錯誤中止」的決定，需要使用者決定。
