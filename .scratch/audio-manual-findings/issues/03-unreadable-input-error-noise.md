# 03: 讀不了的檔案，錯誤訊息夾帶 ffmpeg 的原始輸出

**Status:** resolved

**Found by:** audio#6（壞輸入在呼叫模型之前被拒絕），2026-11-07 實測。優先度低：audio#6 判為通過，因為訊息仍指出是哪個檔案讀不了，也沒有呼叫模型。

## 觀察

內容是文字的 `bad.mp3` 得到：

```
bad.mp3 is not readable audio or video: Could not read media info: 0 @ 0000028b2c62e8c0] Error opening input: Invalid data found when processing input


Error opening input file C:\Users\...\bad.mp3.


Error opening input files: Invalid data found when processing input
```

訊息有 ffmpeg 內部的位址片段、多個空行，並重複檔案的完整路徑。

## 待決定

- 只保留 ffmpeg 輸出的最後一行有意義的原因（`Invalid data found when processing input`），去掉位址與空行。

## 修正（2026-11-15）

`core/ffmpeg.py` 新增 `failure_reason(text)`，用在 `probe`、`_run` 與 `detect_silences` 三處原本直接貼 ffmpeg 輸出尾巴的地方：

- 輸出有「Error opening input files: <原因>」這一行（ffmpeg 打不開輸入時的最後一行）時，只回傳 `<原因>`。
- 其他輸出：去掉每行開頭的 `[mp3 @ 0000019c...]` 位址、空行，各行用 ` | ` 接起來；超過 500 字從前面截掉（錯誤在後面）。

結果（內容是文字的 `bad.mp3`，經真實 ffmpeg 與伺服器）：

```
bad.mp3 is not readable audio or video: Could not read media info: Invalid data found when processing input
```

不存在的檔案由 `InputResolver` 先攔下（「File not found」），不會走到這裡；若走到，原因會是「No such file or directory」。

## 驗證

- 單元測試：用票上的真實 ffmpeg 輸出驗證 `failure_reason`（只剩原因、位址與空行被去掉、過長保留結尾、空輸出），`probe` 對壞檔的訊息整句比對，`transcribe_audio` 對文字檔的訊息不含 `0x`、空行與完整路徑。722 項通過，`ruff` 乾淨。
- audio#6 的預期改為一行原因。
