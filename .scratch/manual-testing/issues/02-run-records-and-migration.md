# 02: Run records, the first record, and removing the old document

**What to build:** every manual run is recorded in its own file that names the environment and lists every checklist item with a result; the image run of 2026-10-30 is kept as the first record; the old image document is gone; and the docs check fails when a record breaks the rules.

- The convention gains the record template, the file name rule (`<server>-YYYY-MM-DD`, with `-2`, `-3`, … for further runs on the same day), the header fields (date, commit hash and clean/dirty note, OS, Python, LiteLLM and Inspector versions, available keys by variable name, approximate cost), the result values (✅, ❌, ⏭), the rule that every checklist item is listed, that ❌ links to a `.scratch/` issue and ⏭ states a reason, the defect process (issue with `Status: needs-triage`, test documents only link to it, a regression item is added after the fix), and the rules on secrets (keys written as `${VAR}`, no key values, account IDs or private endpoints) and on generated images (not committed).
- The record for the image server on 2026-10-30 lists every image checklist item. Items run that day are ✅; the missing-key and `output_dir` items note "found in this run, fixed in commit 26d2520, re-tested"; all others are ⏭ with the missing key as the reason. No issues are opened retroactively.
- The old image document is removed.
- The docs check gains the record rules: file name pattern, the server part names a registered server (entry-point group) or `core`, a checklist exists for it, the record's IDs equal the checklist's IDs exactly, results are one of the three values, every ❌ note links into `.scratch/`, every ⏭ note is non-empty.

**Blocked by:** 01

**Status:** resolved

- [x] The convention contains the record template and every rule listed above
- [x] The record for 2026-10-30 exists, lists exactly the image checklist's IDs, and has a complete header
- [x] The old image document no longer exists and nothing links to it
- [x] The docs check passes on the real record
- [x] The docs check fails on test-built records with a missing ID, an extra ID, a bad file name, an unknown server, an invalid result value, a ❌ without an issue link, and a ⏭ without a reason
- [x] `ruff check .` and `pytest` pass
