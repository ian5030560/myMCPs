# 03: 轉錄的 `timestamps` 與 `language`

**What to build:** 讓 `transcribe_audio` 可以回傳帶時間的逐字稿，並能指定語言。時間相對於原檔，即使給了 `start` 也一樣，agent 因此能指回錄音中的真實位置。

**Blocked by:** 02

**Status:** resolved

- [x] `timestamps=True` 時，每個 segment 前加上 `[hh:mm:ss]`
- [x] 帶 `start` 時，顯示的時間仍相對於原檔（已加上 `start` 的位移）
- [x] 要求時間戳但模型沒有給時，回傳明確錯誤，而不是無標記的逐字稿
- [x] OpenAI 只有 `whisper-1` 會回傳時間（verbose 格式）；其他模型要求 `timestamps` 時走上一條錯誤
- [x] `language` 傳給模型；`language` 只存在於 `transcribe_audio`
