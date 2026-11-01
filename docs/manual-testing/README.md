# 手動測試

自動測試只用 mock，無法證明伺服器真的能和供應商一起運作。這個資料夾記錄那些 mock 測不到的檢查。撰寫規則見 [docs/agents/manual-testing.md](../agents/manual-testing.md)。

- 每個有呼叫模型的工具的伺服器，各有一份清單：[image.md](image.md)。
- 這份文件是所有伺服器共用的操作說明。

## 使用 MCP Inspector

- 工具：[MCP Inspector](https://github.com/modelcontextprotocol/inspector) **2.11.0**（釘版本，發佈已超過兩週）。
- 環境變數 `MYMCPS_CONFIG` 指向設定檔；金鑰放在 shell 環境，或用 `-e` 帶進去。

### 命令列模式（可腳本化，適合重複執行）

```bash
npx -y @modelcontextprotocol/inspector@2.11.0 --cli <伺服器指令> -e MYMCPS_CONFIG=<設定檔絕對路徑> --method tools/list
```

```bash
npx -y @modelcontextprotocol/inspector@2.11.0 --cli <伺服器指令> -e MYMCPS_CONFIG=<設定檔絕對路徑> --method tools/call --tool-name generate_image --tool-arg prompt=cat
```

`<伺服器指令>` 是 `.venv` 裡的 `mymcps-<伺服器名>`，例如 `C:/myMCPs/.venv/Scripts/mymcps-image.exe`。

使用上的三個坑：

1. **設定檔要用 `-e MYMCPS_CONFIG=...` 傳**。Inspector 自己也有 `--config`，寫在伺服器指令後面會被它吃掉，出現「--config cannot be combined with an ad-hoc server」。
2. **伺服器指令要放在 `--tool-arg` 之前**。`--tool-arg` 會吃掉後面所有參數，指令放後面會出現「Invalid parameter format」。
3. **`-e KEY=` 不能給空值**。要模擬「沒有金鑰」，就確認 shell 裡沒設那個環境變數，不要傳空字串。

### 帶金鑰與不帶金鑰

- 帶金鑰：`-e GEMINI_API_KEY=...`，或事先設在 shell 環境裡。
- 不帶金鑰：確認 shell 裡沒有那個變數（見第 3 個坑）。這是測錯誤路徑的方式。

### 網頁介面（適合看圖片預覽）

```bash
npx -y @modelcontextprotocol/inspector@2.11.0
```

在介面選 STDIO，Command 填伺服器指令的完整路徑，Environment Variables 加 `MYMCPS_CONFIG` 和金鑰。工具回傳的縮圖可以直接在 Tools 頁看到，命令列模式則只有 base64。

### 觀察重點

- 伺服器的 stderr：載入了哪些設定檔、啟動警告、LiteLLM 的錯誤。
- 工具回傳的 `isError`，以及錯誤文字是否可讀。
- 輸出資料夾裡的檔案：能開啟、尺寸合理。
