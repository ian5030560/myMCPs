# 01: Convention, shared how-to and the image checklist

**What to build:** a maintainer or agent can open the agent docs folder and find one written convention for manual testing; follow it to the shared how-to and to the image checklist, whose items have stable IDs; and a docs check fails when a checklist breaks the mechanical rules.

- The convention (English, next to the issue-tracker and triage docs) states the scope (only what mocks cannot prove), the folder layout, the checklist template, the `#N` numbering rules (per server, never renumbered or reused, topics are headings only, full form `<server>#N` with a short description in issues and commits), the "requirements" column values, when a run is required (LiteLLM upgrade, vendor-specific code changes, a new tool), and when a server's checklist is created (first tool that calls a model).
- The shared how-to (Traditional Chinese) holds the pinned Inspector usage, its three pitfalls, and how to pass or withhold keys, moved out of the old image document.
- The image checklist (Traditional Chinese) has a config template and items with the columns ID, check, steps/input, expected, requirements, and no status column. The `output_dir` item moves under a heading shared by all tools. The run order and limitations are kept and rewritten with the new IDs. No `core` checklist is created in this ticket.
- `CLAUDE.md` gets a short "Manual testing" subsection under "Agent skills"; the README links to the manual-testing folder.
- The docs check (one new test module) reads every checklist and fails on duplicate or malformed IDs and on an empty requirements cell.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] The convention exists, is in English, and contains the checklist template and every rule listed above
- [ ] The shared how-to names the Inspector version, the three pitfalls, and how to pass and withhold keys
- [ ] The image checklist carries every check from the old image document under `#N` IDs, with a requirements value on each and no status column
- [ ] `CLAUDE.md` points to the convention and the README links to the manual-testing folder
- [ ] The docs check passes on the real image checklist
- [ ] The docs check fails on test-built checklists with a duplicate ID, a malformed ID, and an empty requirements cell (fixtures are built in temporary directories by the test)
- [ ] `ruff check .` and `pytest` pass
