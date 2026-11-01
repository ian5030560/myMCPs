# Manual Testing

How manual tests are written down in this repo. Read this before you create or change anything under `docs/manual-testing/`.

## Scope

Manual testing covers only what the automated tests cannot prove: real provider APIs, the real stdio transport, the real file system, and platform differences. The suite uses mocks (`FakeLiteLLM`), so a green suite says nothing about how LiteLLM or a vendor really behaves. Do not repeat there what a mock test already checks.

## Layout

```
docs/manual-testing/
├── README.md              shared how-to: running a server under MCP Inspector
├── <server>.md            one checklist per server, named after the server
├── core.md                checks that span servers (create it only when one exists)
├── runs/                  one record per run
└── assets/                small committed input files for the checks
```

- A server gets its checklist when it gets its first tool that calls a model. Do not create an empty one.
- The how-to, checklists and records are written in Traditional Chinese. Identifiers, commands and original error messages stay in English. This document stays in English like the rest of `docs/agents/`.

## Checklist

A checklist holds a config template, then items grouped under topic headings. An item is one row of a table with exactly these columns:

```markdown
### generate_image

| ID | 檢查 | 步驟／輸入 | 預期 | 需求 |
|---|---|---|---|---|
| #9 | 沒有金鑰 | 不設任何金鑰，呼叫 `generate_image` | 可讀的錯誤，指出要設哪個環境變數 | 無 |
| #10 | Gemini，只給 prompt | `prompt=cat` | 回傳路徑與預覽，檔案可開啟 | `GEMINI_API_KEY`、會計費 |
```

- A checklist has no status column. Results belong in run records, so the checklist can never contradict the latest run.
- **Requirements** is never empty. Write the variable name of each key the item needs (`GEMINI_API_KEY`), `會計費` when it costs money, or `無`. This lets a tester filter the items they can run right now.

### IDs

- Every item has an ID `#N`, numbered per checklist in one increasing sequence. The checklist's server is the namespace.
- An ID is never renumbered and never reused. When an item is deleted its number stays unused; a new item takes the next number.
- Topics are headings only. Moving an item to another heading does not change its ID.
- Outside the checklist, write the full form `<server>#N` and add a short description, for example `image#18` (Gemini mask composite), so a reader knows which check is meant without opening the file.

## Run records

Every run gets its own file in `runs/`, named `<server>-YYYY-MM-DD.md`. A second run on the same day adds `-2`, `-3`, … (`image-2026-11-02-2.md`). The server part is the checklist's server name (or `core`).

A record starts with the facts that make the run reproducible, then one table:

```markdown
# image 實測紀錄 2026-11-02

- 日期：2026-11-02
- Commit：`a1b2c3d`（乾淨；有未 commit 的修改就寫「有未 commit 的修改」）
- 環境：Windows 11、Python 3.10、LiteLLM 1.104.0、MCP Inspector 2.11.0
- 可用金鑰：`GEMINI_API_KEY`
- 約略花費：US$0.20

| ID | 結果 | 備註 |
|---|---|---|
| #1 | ✅ | |
| #13 | ⏭ | 沒有 OpenAI 金鑰 |
| #18 | ❌ | 右邊的像素被改動。[.scratch/image-mask-shift/issues/01-gemini-mask-shift.md](../../../.scratch/image-mask-shift/issues/01-gemini-mask-shift.md) |
```

- The table lists **every** item of the checklist, no more and no less. Otherwise "not run" and "forgotten" look the same.
- A result is `✅` passed, `❌` failed or `⏭` skipped.
- A `⏭` states why in the notes (for example the missing key). A `❌` links to a `.scratch/` issue.
- The LiteLLM version matters: a result from an older version says nothing about a newer one.

## Defects

A defect found by hand becomes an issue in `.scratch/` with `Status: needs-triage` (see `issue-tracker.md`). The record and the checklist only link to it; they never describe the fix. After the fix, add a checklist item that would have caught the defect, or reword the item that did.

## Secrets and artifacts

- Records and checklists never contain key values, account IDs or private endpoint URLs. Quote keys in config as `${VAR}`.
- Generated images are not committed. Write what you observed in the notes.

## Assets

`assets/` holds the small input files every run uses, so results are comparable between runs. `photo.png` is a 512×512 picture and `mask.png` the same size, left half white (edit), right half black (keep), following the project's mask convention. Refer to them by name from checklists; do not describe how to prepare images.

## When a run is required

A tester runs the affected checklist, and adds a record, when:

1. LiteLLM is upgraded (it is pinned exactly because its routing changes between versions, ADR 0003).
2. Vendor-specific behaviour changes: mask conversion, the Stability one-image loop, provider routing or key resolution.
3. A tool is added.

At any other time a run is optional.
