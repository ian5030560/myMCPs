# 04: 長錄音分 chunk 轉錄

**What to build:** 壓縮後的檔案仍超過廠商大小上限時，工具自動把錄音切成 chunk，逐一轉錄，再合併成一份時間連續的逐字稿。agent 不需要知道任何廠商限制。切點用 ffmpeg `silencedetect` 找靜音，交給切點規劃決定。

**Blocked by:** 01, 03

**Status:** resolved

- [x] 壓縮後未超過上限的錄音仍是單一請求，不切
- [x] 超過上限時以 `silencedetect` 偵測靜音，用切點規劃產生 chunk；每個 chunk 不超過上限
- [x] 每個 chunk 的 segment 時間加上 chunk 的起點，整份逐字稿落在原檔時間軸上
- [x] 被廠商拒絕的 chunk，在結果或錯誤中以時間範圍報告，絕不默默丟棄
- [x] 帶 `start`/`end` 時，切點與位移都以原檔為基準
- [x] 以 lavfi 合成「音訊加指定位置靜音」的 `ffmpeg` 標記測試：chunk 數量與切點落在靜音處、時間位移正確、被拒絕的 chunk 被回報
- [x] 所有 chunk 暫存檔在成功與失敗後都被清除
