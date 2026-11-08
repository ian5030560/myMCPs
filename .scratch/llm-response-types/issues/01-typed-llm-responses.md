# 01: 在 LLMClient 把 LiteLLM 回應轉成型別

**Status:** needs-triage

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
