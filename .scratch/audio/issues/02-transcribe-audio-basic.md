# 02: `transcribe_audio` 基本版（單一請求）

**What to build:** audio server 的第一個真正的工具。agent 傳入本機路徑或 http(s) URL（可加 `start`/`end`），工具先驗證輸入、壓成 mono 16 kHz 32 kbps mp3，再以一個請求轉錄並回傳文字。同時建立 audio 的測試基礎（第一個切入點：記憶體內 `mcp.Client` 搭配 `FakeLiteLLM` 與真實 ffmpeg）。遵守 ADR 0005。

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] `transcribe_audio` 註冊於 audio server，使用 `transcribe_model`，並可用 `model` 引數覆寫
- [x] 輸入可為本機路徑或 URL；`start`/`end` 接受 `hh:mm:ss`、`mm:ss` 或秒數，只處理該範圍
- [x] 先用 ffmpeg 探測並驗證（可讀、有音訊串流），任何付費呼叫之前完成；壞輸入、下載失敗、無音訊串流都得到可讀錯誤，且假的 LiteLLM 沒有被呼叫
- [x] 送出的是 mono 16 kHz 32 kbps mp3
- [x] 廠商限制表集中在一處（Gemini 內嵌 20 MB、時長 9.5 h；OpenAI 轉錄 25 MB）
- [x] `transcribe_model` 未設定時，錯誤指出該設定名稱；設定的模型不具轉錄能力時，錯誤指出該模型
- [x] 缺 ffmpeg 時，訊息指出要安裝 `audio` extra
- [x] 成功與失敗後暫存檔（下載、壓縮檔）都被清除
- [x] `FakeLiteLLM` 能記錄轉錄呼叫與其音訊內容並回傳可設定的 segment；`make_ctx` 能建 audio server（預設設定 `transcribe_model`、`listen_model`）；以 lavfi 產生音訊的測試標記為 `ffmpeg`
- [x] 匯入 server 仍不會載入 litellm，且不會寫入 stdout
