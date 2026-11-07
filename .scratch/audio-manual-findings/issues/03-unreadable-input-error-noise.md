# 03: 讀不了的檔案，錯誤訊息夾帶 ffmpeg 的原始輸出

**Status:** needs-triage

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
