Status: ready-for-agent

# Manual testing: conventions, layout and a docs check

## Problem Statement

The automated tests use mocks only (`FakeLiteLLM`), so they cannot show that the servers work against real providers. The first manual run of the image tools through MCP Inspector found two defects that every mock test had passed: a garbled, hint-less error for a missing key, and an `output_dir` checked only after the paid call. Manual testing is therefore necessary, but there is no convention for it:

- **There is one ad-hoc document** for the image server. It mixes things with different lifetimes: how to use Inspector (shared by every server), the checklist (long-lived), a status column and a dated run log (snapshots that go stale), and a description of fixed defects (which belongs in an issue).
- **Items are numbered by chapter** (`2.3`, `3.5`). Inserting one item renumbers the rest, so older run notes and issues point at the wrong item.
- **A run is not reproducible from the record.** Nothing records which commit, LiteLLM version, OS or keys were used, though LiteLLM is pinned exactly because its routing changes between versions (ADR 0003).
- **"Not run" and "forgotten" look the same**, because a record can list only the items that were run.
- **Defects found by hand have no home.** They are written into the test document, where nobody triages or closes them.
- **Nothing says when manual testing is required**, so a LiteLLM upgrade or a change to vendor-specific code can ship with only mock coverage.
- **Test assets are prepared ad hoc**, so mask-direction results (white = edit) cannot be compared between runs.
- **Nothing stops secrets from landing in git** when someone pastes a config file or an endpoint into a record.
- **Agents produce most of these documents** and have no rules to follow, so every new server would invent its own format.

## Solution

A written convention, a fixed layout under `docs/`, and one automated check for the mechanical parts of the convention.

- The convention lives with the other agent-facing docs, in English, and contains the templates for a checklist and a run record. `CLAUDE.md` points to it; the README points to the manual-testing folder.
- A manual-testing folder holds a shared how-to (pinned Inspector version, its pitfalls, how to pass keys), one checklist per server that has real tools (plus one for cross-server checks such as config layers), a `runs` folder with one record per run, and a small set of committed assets.
- Checklists and records are written in Traditional Chinese; identifiers, commands and original error messages stay in English.
- Checklist items have stable IDs, numbered per server and never reused; topics are headings only.
- Every run record states its environment and lists every checklist item with a result.
- Defects become issues in `.scratch/`; test documents only link to them.
- The existing image document is migrated into this layout.
- A test module reads the manual-testing folder and fails when a checklist or record breaks the mechanical rules.

## User Stories

1. As a maintainer, I want a single written convention for manual testing, so that every server's manual tests look the same.
2. As an agent, I want the convention in the agent docs folder next to the issue-tracker and triage docs, so that I find it the same way I find the other project conventions.
3. As an agent, I want `CLAUDE.md` to point at the convention, so that I read it before writing or updating manual-test documents.
4. As a user reading the README, I want a link to the manual-testing folder, so that I can see what has been verified against real providers.
5. As a maintainer, I want the scope limited to checks mocks cannot prove (real APIs, the real stdio transport, the real filesystem, platform differences), so that manual testing does not duplicate the automated suite.
6. As a tester, I want one shared how-to for running a server under MCP Inspector, so that the instructions are not copied into every server's checklist.
7. As a tester, I want the how-to to name the exact Inspector version, so that commands behave the same on every run.
8. As a tester, I want the known Inspector pitfalls written down (config via `MYMCPS_CONFIG`, server command before `--tool-arg`, no empty `-e` values), so that I don't rediscover them.
9. As a tester, I want to know how to pass keys and how to simulate a missing key, so that I can test both the success and failure paths.
10. As a tester, I want both the CLI mode (scriptable) and the web UI (image previews) described, so that I can pick the right one for each check.
11. As a tester, I want one checklist per server, so that I test exactly the tools that server exposes.
12. As a tester, I want cross-server checks (config layers, variables, startup logging) in their own checklist, so that they are not repeated per server.
13. As a maintainer, I want a checklist to exist only once a server has its first tool that calls a model, so that an empty checklist never suggests coverage that doesn't exist.
14. As a tester, I want each checklist to include a minimal config template, so that I can start a run without reading the whole README.
15. As a tester, I want every item to have a stable ID that is never renumbered or reused, so that records and issues keep pointing at the right check.
16. As a maintainer, I want IDs numbered per server rather than prefixed by topic, so that moving an item between topic headings never changes its ID.
17. As a reader of an issue or commit message, I want items referenced in full form with a short description (for example `image#12` (Gemini mask composite)), so that I know which server and which check is meant without opening the file.
18. As a tester, I want topics organised by headings only, so that the checklist can be reorganised freely.
19. As a tester, I want each item to state the check, the steps or input, and the expected result, so that two testers run it the same way.
20. As a tester, I want each item to state its requirements (which key, whether it costs money, or none), so that I can pick the items I can run right now.
21. As a tester without any keys, I want to filter the items that need nothing, so that I can still run a useful subset for free.
22. As a tester, I want items that cost money marked as such, so that I am never surprised by a bill.
23. As a maintainer, I want no status column in the checklist, so that the checklist never contradicts the latest record.
24. As a tester, I want a new record file for every run, named by server and ISO date, so that runs sort chronologically and never overwrite each other.
25. As a tester running twice on the same day, I want a numeric suffix on the file name, so that the second run gets its own record.
26. As a reviewer, I want every record to state the date, commit hash and whether there were uncommitted changes, so that I know exactly which code was tested.
27. As a reviewer, I want every record to state the OS, Python, LiteLLM and Inspector versions, so that I can tell which results predate an upgrade.
28. As a reviewer, I want every record to list which keys were available, by variable name only, so that I understand why items were skipped.
29. As a maintainer, I want every record to state the approximate cost, so that I can judge how often a full run is affordable.
30. As a reviewer, I want every record to list every checklist item, so that "not run" and "forgotten" are distinguishable.
31. As a reviewer, I want each result to be passed, failed or skipped, so that records are uniform and easy to scan.
32. As a reviewer, I want every skipped item to carry a reason (for example no OpenAI key), so that I know what is needed to cover it.
33. As a maintainer, I want every failed item to link to an issue in `.scratch/`, so that every defect found by hand is triaged.
34. As a tester who finds a defect, I want to open an issue with `Status: needs-triage` and only link to it from the record, so that the fix is tracked where all other work is tracked.
35. As a maintainer, I want a regression check added to the checklist once a manually found defect is fixed, so that the defect is checked again on later runs.
36. As a maintainer, I want records to contain no key values, account IDs or private endpoint URLs, so that committing a record never leaks a secret.
37. As a tester quoting a config file, I want keys written as `${VAR}`, so that the record shows how the key was supplied without showing the key.
38. As a maintainer, I want generated images kept out of git, with observations written in the notes instead, so that the repository stays small.
39. As a tester, I want a small committed photo and mask (512×512; left half white, right half black), so that every run uses identical inputs and mask results are comparable.
40. As a maintainer, I want manual testing required when LiteLLM is upgraded, so that routing changes between versions are caught.
41. As a maintainer, I want manual testing required when vendor-specific code changes (mask conversion, the Stability loop, provider routing), so that the code mocks cover least is checked for real.
42. As a maintainer, I want manual testing required when a tool is added, so that every tool is checked at least once against a real provider.
43. As a maintainer, I want manual testing optional at all other times, so that the convention does not slow down unrelated work.
44. As an agent, I want the checklist and record templates inside the convention, so that one read gives me everything I need.
45. As an agent, I want the docs check to fail when I break a mechanical rule, so that I learn about the mistake before review.
46. As a maintainer, I want the docs check to verify that IDs in a checklist are unique and well formed and that every item states its requirements, so that checklists stay referenceable.
47. As a maintainer, I want the docs check to verify that every record lists exactly the IDs of its checklist, so that no item is silently dropped or invented.
48. As a maintainer, I want the docs check to verify result values, issue links on failures and reasons on skips, so that records stay uniform.
49. As a maintainer, I want the docs check to verify record file names and that the server part names a registered server or `core`, so that records cannot drift from the server list.
50. As a maintainer, I want the docs check to verify that the committed mask means "edit the left half, keep the right half" under the project's mask convention and matches the photo's size, so that the assets cannot silently invert the test.
51. As a maintainer, I want the existing image document migrated into the new layout, so that there is one format from the start.
52. As a reviewer, I want the image run of 2026-10-30 kept as the first record, with the two defects it found noted as fixed in commit 26d2520, so that the history is preserved without retroactive issues.

## Implementation Decisions

- **Layout is the contract.** The convention defines these locations, and the docs check reads them:
  - the convention: in the agent docs folder, English;
  - the manual-testing folder under `docs`: a shared how-to (its README), one checklist per server named after the server, a `core` checklist for cross-server checks, a `runs` folder, and an `assets` folder;
  - record file names: `<server>-YYYY-MM-DD.md`, with `-2`, `-3`, … for further runs on the same day.
- **Language**: convention in English, like the other agent docs; how-to, checklists and records in Traditional Chinese, keeping identifiers, commands and original error messages in English.
- **Checklist format**: a config template, then items grouped under topic headings. Each item is a table row with the columns ID, check, steps/input, expected, requirements. No status column.
- **IDs**: written `#N` in the checklist, numbered per server (and per the `core` checklist) in one increasing sequence; deleted numbers are never reused. The server is the namespace because the file is: the full form is `<server>#N`, used in issues and commit messages with a short description. Records name their server in the file name, so their tables use `#N`.
- **Requirements column** values are short and filterable: a key's variable name (for example `GEMINI_API_KEY`), `會計費` when the item costs money, or `無`.
- **Record format**: a header with date, commit hash plus a clean/dirty note, OS, Python, LiteLLM and Inspector versions, available keys by variable name, approximate cost; then one table with the columns ID, result, notes covering every checklist item. Results are ✅, ❌ or ⏭. ❌ requires a link to a `.scratch/` issue; ⏭ requires a reason.
- **Defects**: a manually found defect becomes a `.scratch/` issue with `Status: needs-triage` (see the issue-tracker and triage-label docs). Test documents never describe fixes. After the fix, a regression item is added to the checklist (or an existing item is reworded to cover it).
- **Secrets and artifacts**: no key values, account IDs or private endpoint URLs in any manual-testing document; keys in quoted config are written as `${VAR}`; generated outputs are not committed.
- **Assets**: a small photo and a mask of the same size (512×512; left half white = edit, right half black = keep), committed as small PNG files and generated once.
- **When a run is required**: on a LiteLLM upgrade (ADR 0003), on changes to vendor-specific behaviour (mask conversion, the Stability one-image loop, provider routing and key resolution), and when a tool is added. Otherwise optional.
- **When a checklist is created**: when a server gets its first tool that calls a model. `video` and `audio` get none yet.
- **Templates**: the checklist and record templates are inline in the convention; there are no separate template files.
- **`CLAUDE.md`** gains a short "Manual testing" subsection under "Agent skills" pointing at the convention, in the style of the existing subsections. The README gains one link to the manual-testing folder.
- **Migration of the existing image document**:
  - Checklist items move to the image checklist with new `#N` IDs, in the existing order, and lose the status column. The `output_dir` item, which applies to every tool, moves under a shared topic heading.
  - The "how to test" section moves to the shared how-to.
  - The executed-test log becomes the first record for 2026-10-30: items run then are ✅; the missing-key and `output_dir` items note "found in this run, fixed in commit 26d2520, re-tested"; all other items are ⏭ with their missing key as the reason. No issues are opened retroactively.
  - The run-order and limitations sections stay in the image checklist, rewritten to use the new IDs.
  - The old document is removed.
- **Docs check**: one new test module, the only new test seam. It reads the manual-testing folder and does not import or exercise server code, except the mask convention for the asset check. It parses the Markdown tables of checklists and records by their column headers, so the table formats above are fixed. The set of valid server names comes from the `mymcps.servers` entry-point group (as in the existing name-uniqueness test) plus `core`.

## Testing Decisions

- A good test here checks what a reader relies on, not how the documents are worded: that IDs resolve, that records are complete, that a failure always leads to an issue, that the assets mean what the checklist says. It must not check prose, headings other than the tables, or the order of items.
- **One seam: the docs check.** It covers:
  - checklists: IDs unique and of the form `#N`; every row has a non-empty requirements cell;
  - records: file name matches the pattern and names a registered server or `core`; a checklist exists for that server; the set of IDs equals the checklist's set; every result is ✅, ❌ or ⏭; every ❌ note contains a link into `.scratch/`; every ⏭ note is non-empty;
  - assets: the photo and mask exist and have the same size; loading the mask through the project's mask type gives "edit" on the left half and "keep" on the right half.
- Not checked automatically (left to review): that IDs are never reused after deletion, that no secrets appear, that the stated environment is true, and that a record exists whenever a run was required.
- Prior art: the entry-point name-uniqueness test (iterating `mymcps.servers`) for the server list; the mask tests in the image test package for loading a mask and checking which side is edited; the conftest helpers for image bytes.
- The check must pass on the migrated image checklist and its 2026-10-30 record, and fail on a fixture copy with a missing ID, a ❌ without a link, a ⏭ without a reason, and a bad file name. Fixtures live in temporary directories built by the test, not in the repository.

## Out of Scope

- Running the remaining image items against real providers (Gemini, Stability, OpenAI). This spec sets up the convention; filling in results is ordinary manual testing afterwards.
- Checklists for `video` and `audio`, which have no model-calling tools yet.
- A release process or pre-release smoke test.
- Automating the manual runs themselves (scripted Inspector calls, CI jobs with real keys).
- Secret scanning of the documents.
- Changes to server code or the automated test suite beyond the docs check.

## Further Notes

- The two defects in the first run came from behaviour of real LiteLLM that `FakeLiteLLM` does not imitate (a missing key reported as `APIConnectionError` with an embedded traceback). That is the case for keeping manual runs on LiteLLM upgrades even when the mock suite is green.
- MCP Inspector is pinned to 2.11.0 in the current document; the how-to keeps that pin, and a version change is a reason to update the how-to's pitfalls.
- Stable IDs were chosen over chapter numbers and over topic prefixes (`gen-3`) because both encode where an item sits, which changes; the server cannot change.
