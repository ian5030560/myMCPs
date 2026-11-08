# 07: README 與 audio 實測清單

**What to build:** 讓使用者與測試者找得到新的 audio 工具：README 說明工具與設定；依手動測試規範建立 audio 的實測清單，符合「新增工具必須實測」的規定。

**Blocked by:** 04, 06

**Status:** resolved

- [x] README 說明 `transcribe_audio`、`listen_audio`、`transcribe_model`／`listen_model` 設定與 `audio` extra
- [x] 讀過 `docs/agents/manual-testing.md` 後建立 `docs/manual-testing/audio.md`：設定範本、`#N` ID、需求欄；涵蓋真實供應商才驗得到的項目（壓縮格式被接受、Files API 上傳與刪除、真實時間戳、長錄音分 chunk、錯誤訊息）
- [x] 清單必須涵蓋實作時無法用假的 LiteLLM 驗證的風險，每一項都有對應的 ID：
  - Gemini 上傳後檔案是否還在處理中（`PROCESSING`），詢問是否因此失敗；若會，需補輪詢檔案狀態的票
  - 檔案參照的 `format`（`audio/mpeg`）是否被 LiteLLM 與 Gemini 接受
  - Gemini 轉錄模型回傳的逐字（`words`）欄位：`word` 是否已含空格或標點、中文是否被正確接字、`timestamp_granularities=["word"]` 是否真的帶回時間
  - 停頓 0.8 秒與 10 秒上限分出來的行是否合理（對照真實錄音）
  - `listen_audio` 的 `timestamps`：模型是否照 `[hh:mm:ss]` 格式、是否從這段音訊的 0 秒算起（給 `start` 後對照真實位置）
  - 長錄音分 chunk：切點是否落在說話停頓處、chunk 接縫處是否掉字、mp3 `-c copy` 切點造成的時間偏差有多大
  - 被廠商拒絕的 chunk 的標記，與限流發生在中途時的行為（寫票時是「已完成的 chunk 結果會遺失，沒有重試」；實測後依 [audio-manual-findings 04](../../audio-manual-findings/issues/04-chunk-rate-limit.md) 改為等待後重送，用盡才標記）
  - 32 kbps mono 16 kHz mp3 的辨識品質與 Gemini／OpenAI 是否接受此格式
- [x] 需要的測試音檔（若有）放入 `docs/manual-testing/assets/`，且體積小
- [x] `tests/docs` 的文件檢查通過
- [x] 不含實測紀錄；有金鑰時另外執行並記錄
