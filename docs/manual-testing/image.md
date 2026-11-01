# 圖片伺服器實測清單

`mymcps-image` 的 mock 測試無法證明它能和真實供應商一起運作，這份清單列出需要手動驗證的檢查。操作方式見 [README.md](README.md)；撰寫規則見 [docs/agents/manual-testing.md](../agents/manual-testing.md)。

項目的結果不寫在這裡，每次執行另外記錄在 `runs/`。引用項目時寫 `image#N` 並附簡短描述。

## 設定檔範本

最小設定（Gemini）：

```toml
output_dir = "C:/path/to/mymcps-out"

[image]
gen_model  = "gemini/gemini-3.1-flash-image"
edit_model = "gemini/gemini-3.1-flash-image"
```

測 Stability 時，呼叫時傳 `model="stability/sd3.5-large"`，不必改設定檔。

測試素材：[assets/photo.png](assets/photo.png)（512×512）和 [assets/mask.png](assets/mask.png)（同尺寸，左半白＝改，右半黑＝留）。工具的路徑參數請給它們的絕對路徑。

## 清單

### 啟動與 `list_models`

| ID | 檢查 | 步驟／輸入 | 預期 | 需求 |
|---|---|---|---|---|
| #1 | 啟動 | 用範本設定檔啟動伺服器，看 stderr 與 stdout | stderr 列出載入的檔案；stdout 沒有雜訊；不出現 Traceback | 無 |
| #2 | 沒有 Stability 金鑰時的工具清單 | `tools/list` | 只有 `list_models`、`generate_image`、`edit_image` | 無 |
| #3 | `list_models` | 呼叫 `list_models` | 兩個用途顯示設定的模型；沒有金鑰或端點 | 無 |
| #4 | 設定檔有誤 | 把區段寫成 `[imgae]` 後啟動 | 啟動失敗，stderr 指出檔案、區段與欄位，客戶端看到「Connection closed」 | 無 |
| #5 | 用途設到不支援的模型 | 把 `gen_model` 設成 `gpt-4o` 後啟動 | 啟動時警告，伺服器照常啟動 | 無 |
| #6 | 別名缺金鑰時的 `key_configured` | 設一個別名，不提供它的金鑰，呼叫 `list_models` | 該別名的 `key_configured` 為 false | 無 |

### 所有工具共用

| ID | 檢查 | 步驟／輸入 | 預期 | 需求 |
|---|---|---|---|---|
| #7 | `output_dir` 不合法時在呼叫前被拒絕 | 對 `generate_image`、`edit_image` 傳 `output_dir="/tmp/x"` 與 `"../x"`，不設任何金鑰 | 被拒絕，訊息說明 `output_dir` 的問題，而不是缺金鑰；**而且不應已經花錢** | 無 |

### `generate_image`

| ID | 檢查 | 步驟／輸入 | 預期 | 需求 |
|---|---|---|---|---|
| #8 | 用途沒設定模型 | 設定檔不寫 `gen_model`，呼叫 `generate_image` | 錯誤訊息指出 `gen_model` 與 `[image]` 區段 | 無 |
| #9 | 沒有金鑰 | 不設任何金鑰，呼叫 `generate_image` | 可讀的一行錯誤，指出要設哪個環境變數，沒有 Traceback | 無 |
| #10 | Gemini，只給 prompt | `prompt=cat` | 回傳路徑與預覽，檔案可開啟 | `GEMINI_API_KEY`、會計費 |
| #11 | Stability 一次多張 | `model="stability/sd3.5-large"`，`n=3` | 三次獨立呼叫、三個不同檔名 | `STABILITY_API_KEY`、會計費 |
| #12 | 輸出子資料夾 | `output_dir="logos"` | 存到輸出資料夾的 `logos` 子資料夾 | `GEMINI_API_KEY`、會計費 |
| #13 | OpenAI 的 `n`、`size`、`quality` | `n=2`，加上 `size`、`quality` | 一次呼叫出兩張；尺寸符合 | `OPENAI_API_KEY`、會計費 |

### `edit_image`

| ID | 檢查 | 步驟／輸入 | 預期 | 需求 |
|---|---|---|---|---|
| #14 | 圖片路徑不存在 | `image` 給不存在的路徑 | `File not found: ...` | 無 |
| #15 | Stability 模型、沒有遮罩 | `model="stability/..."`，不給 `mask` | 說明需要遮罩，並建議改用其他模型或 `stability_edit` | 無 |
| #16 | Stability 模型、給參考圖 | `model="stability/..."`，給 `references` | 說明 Stability 一次只編輯一張圖 | 無 |
| #17 | Gemini 無遮罩 | 給圖片與 prompt | 成功 | `GEMINI_API_KEY`、會計費 |
| #18 | **Gemini 有遮罩** | `photo.png`、`mask.png` 與 prompt | 遮罩外的像素與原圖**逐像素相同**；遮罩內有變化；邊界沒有位移 | `GEMINI_API_KEY`、會計費 |
| #19 | Stability 有遮罩 | `model="stability/..."`，`photo.png` 與 `mask.png` | 走 inpaint，成功 | `STABILITY_API_KEY`、會計費 |
| #20 | 遮罩尺寸與原圖不同 | 給尺寸不同的遮罩 | 正確縮放，或給清楚的錯誤 | `GEMINI_API_KEY`、會計費 |
| #21 | 圖片用 http(s) URL | `image` 給圖片網址 | 成功，暫存檔被清掉 | `GEMINI_API_KEY`、會計費 |
| #22 | 非圖片檔當 `image` | `image` 給文字檔 | 可讀的錯誤，不是 Traceback | 無 |
| #23 | **OpenAI 有遮罩（白 = 改）** | `model="openai/..."`，`photo.png` 與 `mask.png` | 只有白色那半改變；轉成「透明 = 改」的方向正確 | `OPENAI_API_KEY`、會計費 |
| #24 | OpenAI 無遮罩、給參考圖 | `model="openai/..."`，給 `references` | 成功 | `OPENAI_API_KEY`、會計費 |

### `stability_edit`

| ID | 檢查 | 步驟／輸入 | 預期 | 需求 |
|---|---|---|---|---|
| #25 | 沒有金鑰時看工具清單 | 不設 Stability 金鑰，`tools/list` | 沒有 `stability_edit` | 無 |
| #26 | 有金鑰時看工具清單 | 設 `STABILITY_API_KEY` 或 `[providers.stability] api_key`，`tools/list` | 工具出現 | `STABILITY_API_KEY` |
| #27 | `remove_background` | `operation=remove_background` | 成功 | `STABILITY_API_KEY`、會計費 |
| #28 | `erase`，帶遮罩 | `operation=erase`，`photo.png` 與 `mask.png`，`grow_mask=3` | 遮罩區被清掉 | `STABILITY_API_KEY`、會計費 |
| #29 | `outpaint` 只給一個方向 | `operation=outpaint`，只給 `left=200` | 只向左擴 | `STABILITY_API_KEY`、會計費 |
| #30 | `search_and_replace` 缺參數 | 不給 `search_prompt` | 不呼叫 API，直接說明缺什麼 | 無 |
| #31 | `search_and_recolor` | `operation=search_and_recolor`，給 `prompt` 與 `select_prompt` | 成功 | `STABILITY_API_KEY`、會計費 |
| #32 | 放大 | `upscale_fast`、`upscale_conservative` | 成功，解析度提高 | `STABILITY_API_KEY`、會計費 |
| #33 | Stability 走代理端點 | `[providers.stability]` 指向代理端點 | 請求確實走代理 | `STABILITY_API_KEY`、會計費 |

### Provider 與金鑰路由

#34 與 #35 不需要真的 OpenAI 金鑰：起一個假的本機 HTTP 服務，只印出請求標頭，用假金鑰測路由即可。

| ID | 檢查 | 步驟／輸入 | 預期 | 需求 |
|---|---|---|---|---|
| #34 | 自架端點：provider 加別名連結 | provider 設 `api_base` 指向假服務，別名用 `provider` 連結它 | 請求送到該端點，帶 provider 的金鑰 | 無 |
| #35 | 官方金鑰不會送到自架端點 | 同時設 `OPENAI_API_KEY`，呼叫時傳 raw 字串 `openai/...` | 仍走官方端點，**自架端點收不到 OpenAI 金鑰** | 無 |
| #36 | provider 與別名的 `extra` 衝突 | 兩邊設同一個 `extra` 欄位、不同的值 | 別名的值生效 | 無 |

## 建議的執行順序

1. Gemini 金鑰：#5、#6 → #10 → #17 → **#18**。
2. Stability 金鑰：#11 → #19 → #25～#33。
3. 假的本機服務驗證 #34、#35。
4. 取得 OpenAI 金鑰後補 #13、#23、#24。

不需要金鑰的項目（需求為「無」）隨時可以跑，不會花錢。

## 這份清單不能證明的事

- 各供應商的模型名稱與帳號權限（只能看到實際回應）。
- `size`、`quality`、`n` 被 LiteLLM 忽略或改寫的方式，要以實際出圖為準。
- macOS 行為。
