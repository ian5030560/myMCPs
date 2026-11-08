# 01: 在 LLMClient 把 LiteLLM 回應轉成型別

**Status:** resolved

**Found by:** audio 重構的物件導向評估，2026-11-08。

## 問題

LiteLLM 的回應有時是物件、有時是字典，各處自己處理：`image/results.py`（`_field`）、`audio/transcriber.py` 與 `audio/listener.py`（已改用 `core/responses.field`）。`core/llm.py` 是唯一匯入 litellm 的模組，轉換最該發生在那裡。

## 想法

`LLMClient` 回傳小型值物件（例如轉錄：文字、`Segment` 清單、`Word` 清單；對話：答案文字；圖片：b64 或 url 清單），呼叫端不再知道 LiteLLM 的回應長相，`core/responses.field` 即可刪除。

## 刪除測試

刪掉 `field` 時，三處重複的「字典或物件」會回來；在接縫處轉換一次，三處都不用知道。

## 範圍與風險

- 動到核心與 image；`FakeLiteLLM` 與各測試的假回應格式要一起確認。
- 單獨驗證：`pytest` 全過，並用真實 API 各跑一次 image 與 audio（見 `docs/manual-testing/`）。

## 完成

- `core/responses.py`：`Segment`、`Word`、`Transcription`、`GeneratedImage`，以及從 LiteLLM 回應（物件或字典）轉換的函式；`field` 已刪除。
- `LLMClient`：`complete` 回傳答案文字（沒有 choice 時 `ProviderError`），`generate_image`/`edit_image` 回傳 `list[GeneratedImage]`，`transcribe` 回傳 `Transcription`，`upload_file` 回傳檔案 id（沒有時 `ProviderError`），`delete_file` 回傳 None。
- `image/results.py`、`audio/transcriber.py`、`audio/listener.py` 不再碰 LiteLLM 回應；`audio/timestamps` 從 core 取用 `Segment`、`Word`。
- 測試：`test_llm` 新增轉換測試，`test_results` 改用 `GeneratedImage`；其餘測試不變。`pytest` 712 項通過、`ruff` 乾淨。
- 未用真實 API 驗證：轉換只依賴既有欄位名稱（`data[].b64_json/url`、`choices[0].message.content`、`text/segments/words`、`id`），行為與先前相同，但沒有重跑 image 與 audio 的實測清單。
