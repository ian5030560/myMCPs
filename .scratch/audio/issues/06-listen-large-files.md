# 06: `listen_audio` 大檔：Files API 與時長上限

**What to build:** 讓 `listen_audio` 處理超過 Gemini 內嵌上限的長錄音（走 Files API），並在錄音超過時長上限時，用一個說明下一步的錯誤取代失敗，讓 agent 自行決定怎麼拆。

**Blocked by:** 05

**Status:** resolved

- [x] 壓縮後超過 Gemini 內嵌上限時，改用 Files API 上傳再詢問
- [x] 回答之後刪除已上傳的檔案；詢問失敗時也刪除
- [x] `LLMClient` 新增刪除已上傳檔案的方法，仍是唯一匯入 `litellm` 的模組，LiteLLM 例外照舊轉成 `ToolError` 子類別
- [x] 超過時長上限（Gemini 9.5 小時）時，在呼叫模型之前就失敗，錯誤指出兩條路：依序用 `start`/`end` 處理並把筆記帶進下一次的 `prompt`，或先用 `transcribe_audio` 轉錄
- [x] 未知上限的廠商直接內嵌送出，廠商自己的錯誤以可讀方式轉達
- [x] 測試涵蓋：上傳、詢問、刪除的順序與失敗時仍刪除；超過時長上限時沒有任何模型呼叫；錯誤訊息包含兩條路
