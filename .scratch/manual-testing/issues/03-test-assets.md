# 03: Committed test photo and mask

**What to build:** every manual run uses the same input images, so mask results are comparable between runs; and a docs check fails if the mask stops meaning "edit the left half, keep the right half".

- A small 512×512 photo and a same-sized mask (left half white = edit, right half black = keep) are generated once and committed in the manual-testing assets folder.
- The image checklist's config template and steps, and the shared how-to, refer to these two files instead of describing how to prepare images.
- The docs check gains the asset rules: both files exist and have the same size; loading the mask through the project's mask type gives "edit" on the left half and "keep" on the right half.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] The photo and the mask are committed, small, and 512×512
- [ ] The checklist and how-to refer to them and no longer describe preparing images
- [ ] The docs check passes on the real assets
- [ ] The docs check fails on test-built assets with a size mismatch and with the mask mirrored left to right
- [ ] `ruff check .` and `pytest` pass
