# 05: `listen_audio` 基本版（整段送出）

**What to build:** agent 可以對錄音問一個自由文字的問題，並得到答案；整段壓縮後以一個請求送給 `listen_model`，從不切割（ADR 0005）。

**Blocked by:** 02, 03

**Status:** resolved

- [x] `listen_audio(path, prompt, start, end, timestamps, model)` 註冊於 audio server，使用 `listen_model`，並可用 `model` 覆寫
- [x] 與 `transcribe_audio` 共用同一個前處理（輸入解析、驗證、`start`/`end`、壓縮），驗證在任何模型呼叫之前
- [x] `timestamps` 讓答案中引用的時間使用 `[hh:mm:ss]` 且相對於原檔；模型沒有給時間時回傳明確錯誤
- [x] `listen_model` 未設定時，錯誤指出設定名稱；模型不具聽音訊能力時，錯誤指出該模型
- [x] 沒有 `language` 引數，也不寫任何檔案
- [x] 測試涵蓋：送出內容為壓縮後的整段、`start`/`end` 的位移、時間戳格式與無時間戳錯誤、暫存檔清除
