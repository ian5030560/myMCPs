"""The manual-testing documents keep the rules in docs/agents/manual-testing.md."""

import datetime
import io
import re
from importlib.metadata import entry_points
from pathlib import Path

import pytest
from PIL import Image

from mymcps.image.masks import Mask

MANUAL_TESTING = Path(__file__).resolve().parents[2] / "docs" / "manual-testing"
CHECKLIST_COLUMNS = ["ID", "檢查", "步驟／輸入", "預期", "需求"]
ID_FORMAT = re.compile(r"#[1-9]\d*")
RECORD_COLUMNS = ["ID", "結果", "備註"]
RESULTS = {"✅", "❌", "⏭"}
RECORD_NAME = re.compile(r"(?P<server>.+?)-(?P<date>\d{4}-\d{2}-\d{2})(?:-(?P<run>\d+))?\.md")


def checklists() -> list[Path]:
    """Every markdown file in the folder except the shared how-to."""
    return sorted(p for p in MANUAL_TESTING.glob("*.md") if p.name != "README.md")


def table_rows(text: str, first_column: str) -> list[list[str]] | None:
    """The data rows of the table whose header starts with `first_column`; None if no such table."""
    lines = text.splitlines()
    for start, line in enumerate(lines):
        header = _cells(line)
        if header and header[0] == first_column:
            rows = []
            for row in lines[start + 2:]:            # skip the |---| separator
                cells = _cells(row)
                if cells is None:
                    break
                rows.append(cells)
            return rows
    return None


def _cells(line: str) -> list[str] | None:
    line = line.strip()
    if not (line.startswith("|") and line.endswith("|")):
        return None
    return [cell.strip() for cell in line.strip("|").split("|")]


def checklist_problems(text: str) -> list[str]:
    """Everything wrong with one checklist, as readable sentences."""
    rows, problems = [], []
    for start, line in enumerate(text.splitlines()):
        header = _cells(line)
        if header and header[0] == "ID":
            if header != CHECKLIST_COLUMNS:
                problems.append(f"columns are {header}, expected {CHECKLIST_COLUMNS}")
            rows += [r for r in table_rows("\n".join(text.splitlines()[start:]), "ID") or []]
    if not rows:
        return problems + ["no checklist table found"]
    seen: set[str] = set()
    for row in rows:
        if len(row) != len(CHECKLIST_COLUMNS):
            problems.append(
                f"row {row[0]!r} has {len(row)} cells, expected {len(CHECKLIST_COLUMNS)}")
            continue
        item_id, requirements = row[0], row[-1]
        if not ID_FORMAT.fullmatch(item_id):
            problems.append(f"{item_id!r} is not an ID like #12")
        if item_id in seen:
            problems.append(f"{item_id} appears twice")
        seen.add(item_id)
        if not requirements:
            problems.append(f"{item_id} has an empty requirements cell")
    return problems


def test_there_is_a_checklist_for_the_image_server():
    assert MANUAL_TESTING / "image.md" in checklists()


@pytest.mark.parametrize("path", checklists(), ids=lambda p: p.name)
def test_every_checklist_follows_the_rules(path):
    assert checklist_problems(path.read_text(encoding="utf-8")) == []


TABLE = "| ID | 檢查 | 步驟／輸入 | 預期 | 需求 |\n|---|---|---|---|---|\n"


@pytest.mark.parametrize("rows,needle", [
    ("| #1 | a | b | c | 無 |\n| #1 | a | b | c | 無 |\n", "#1 appears twice"),
    ("| 1 | a | b | c | 無 |\n", "not an ID"),
    ("| #01 | a | b | c | 無 |\n", "not an ID"),
    ("| #1 | a | b | c |  |\n", "#1 has an empty requirements cell"),
    ("| #1 | a | b | c |\n", "has 4 cells"),
])
def test_a_broken_checklist_is_reported(rows, needle):
    assert any(needle in p for p in checklist_problems(TABLE + rows))


def test_a_checklist_with_the_wrong_columns_is_reported():
    text = "| ID | 檢查 | 狀態 |\n|---|---|---|\n| #1 | a | ✅ |\n"
    assert any("columns are" in p for p in checklist_problems(text))


def test_a_file_without_a_table_is_reported():
    assert checklist_problems("just prose") == ["no checklist table found"]


def test_ids_must_be_unique_across_all_tables_of_a_checklist():
    def one(n):
        return f"{TABLE}| #{n} | a | b | c | 無 |\n"

    assert checklist_problems(one(1) + "\n## more\n\n" + one(2)) == []
    assert any("#1 appears twice" in p for p in checklist_problems(
        one(1) + "\n## more\n\n" + one(1)))


# ── run records ──────────────────────────────────────────────────────────

def records() -> list[Path]:
    return sorted((MANUAL_TESTING / "runs").glob("*.md"))


def registered_servers() -> set[str]:
    return {ep.name for ep in entry_points(group="mymcps.servers")} | {"core"}


def checklist_ids(text: str) -> set[str]:
    """The IDs of every table in a checklist (it has one table per topic)."""
    lines = text.splitlines()
    ids: set[str] = set()
    for start, line in enumerate(lines):
        if (_cells(line) or [""])[0] == "ID":
            ids |= {row[0] for row in table_rows("\n".join(lines[start:]), "ID") or []}
    return ids


def record_problems(name: str, text: str, checklist_text: str | None) -> list[str]:
    """Everything wrong with one record. `checklist_text` is the server's checklist, if any."""
    problems = []
    match = RECORD_NAME.fullmatch(name)
    if not match:
        return [f"{name} is not named <server>-YYYY-MM-DD[-N].md"]
    try:
        datetime.date.fromisoformat(match["date"])
    except ValueError:
        problems.append(f"{match['date']} is not a real date")
    if match["server"] not in registered_servers():
        problems.append(f"{match['server']!r} is not a registered server or core")
    if checklist_text is None:
        problems.append(f"there is no checklist for {match['server']}")
    header = next((_cells(line) for line in text.splitlines()
                   if (_cells(line) or [""])[0] == "ID"), None)
    if header != RECORD_COLUMNS:
        return problems + [f"columns are {header}, expected {RECORD_COLUMNS}"]
    rows = table_rows(text, "ID") or []
    for row in rows:
        if len(row) != len(RECORD_COLUMNS):
            problems.append(f"row {row[0]!r} has {len(row)} cells, expected 3")
            continue
        item_id, result, notes = row
        if result not in RESULTS:
            problems.append(f"{item_id} has result {result!r}, expected one of {sorted(RESULTS)}")
        if result == "❌" and ".scratch/" not in notes:
            problems.append(f"{item_id} failed but links to no issue in .scratch/")
        if result == "⏭" and not notes:
            problems.append(f"{item_id} was skipped without a reason")
    ids = [row[0] for row in rows]
    for item_id in {i for i in ids if ids.count(i) > 1}:
        problems.append(f"{item_id} appears twice")
    if checklist_text is not None:
        expected = checklist_ids(checklist_text)
        for item_id in sorted(expected - set(ids)):
            problems.append(f"{item_id} is in the checklist but missing from the record")
        for item_id in sorted(set(ids) - expected):
            problems.append(f"{item_id} is in the record but not in the checklist")
    return problems


def checklist_for(path: Path) -> str | None:
    server = RECORD_NAME.fullmatch(path.name)
    target = MANUAL_TESTING / f"{server['server']}.md" if server else None
    return target.read_text(encoding="utf-8") if target and target.exists() else None


def test_there_is_a_record_for_the_first_image_run():
    assert MANUAL_TESTING / "runs" / "image-2026-10-30.md" in records()


@pytest.mark.parametrize("path", records(), ids=lambda p: p.name)
def test_every_record_follows_the_rules(path):
    text = path.read_text(encoding="utf-8")
    assert record_problems(path.name, text, checklist_for(path)) == []


CHECKLIST = TABLE + "| #1 | a | b | c | 無 |\n| #2 | a | b | c | 無 |\n"
RECORD_TABLE = "| ID | 結果 | 備註 |\n|---|---|---|\n"
GOOD_ROWS = "| #1 | ✅ | |\n| #2 | ⏭ | 沒有金鑰 |\n"


def problems_of(rows, name="image-2026-11-02.md", checklist=CHECKLIST, table=RECORD_TABLE):
    return record_problems(name, table + rows, checklist)


def test_a_good_record_has_no_problems():
    assert problems_of(GOOD_ROWS) == []
    assert problems_of(GOOD_ROWS, name="image-2026-11-02-2.md") == []
    link = "[x](../../../.scratch/f/issues/01-x.md)"
    assert problems_of(f"| #1 | ❌ | {link} |\n| #2 | ✅ | |\n") == []


@pytest.mark.parametrize("rows,needle", [
    ("| #1 | ✅ | |\n", "#2 is in the checklist but missing"),
    (GOOD_ROWS + "| #3 | ✅ | |\n", "#3 is in the record but not in the checklist"),
    (GOOD_ROWS + "| #2 | ✅ | |\n", "#2 appears twice"),
    ("| #1 | ✔ | |\n| #2 | ✅ | |\n", "has result"),
    ("| #1 | ❌ | 壞了 |\n| #2 | ✅ | |\n", "links to no issue"),
    ("| #1 | ⏭ | |\n| #2 | ✅ | |\n", "skipped without a reason"),
    ("| #1 | ✅ |\n| #2 | ✅ | |\n", "has 2 cells"),
])
def test_a_broken_record_is_reported(rows, needle):
    assert any(needle in p for p in problems_of(rows))


@pytest.mark.parametrize("name,needle", [
    ("image-26-11-02.md", "is not named"),
    ("image-2026-11-02.txt", "is not named"),
    ("image-2026-13-40.md", "not a real date"),
    ("nonsense-2026-11-02.md", "not a registered server"),
])
def test_a_badly_named_record_is_reported(name, needle):
    assert any(needle in p for p in problems_of(GOOD_ROWS, name=name))


def test_a_record_without_a_checklist_is_reported():
    assert any("no checklist for image" in p for p in problems_of(GOOD_ROWS, checklist=None))


def test_a_record_with_the_wrong_columns_is_reported():
    table = "| ID | 狀態 |\n|---|---|\n"
    assert any("columns are" in p for p in problems_of("| #1 | ✅ |\n", table=table))


# ── assets ───────────────────────────────────────────────────────────────

def asset_problems(photo: bytes, mask: bytes) -> list[str]:
    """The photo and the mask must match in size, and the mask must edit the left half."""
    photo_size = Image.open(io.BytesIO(photo)).size
    if Image.open(io.BytesIO(mask)).size != photo_size:
        return ["the mask and the photo differ in size"]
    to_edit = Image.open(io.BytesIO(Mask.load(mask, photo_size).to_stability_png()))
    width, height = photo_size
    left, right = to_edit.getpixel((width // 4, height // 2)), to_edit.getpixel(
        (3 * width // 4, height // 2))
    if (left, right) != (255, 0):
        return [f"the mask must edit the left half and keep the right, got {left}/{right}"]
    return []


def png(size, fill=0, left=None) -> bytes:
    img = Image.new("L", size, fill)
    if left is not None:
        img.paste(left, (0, 0, size[0] // 2, size[1]))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_the_committed_assets_are_consistent():
    assets = MANUAL_TESTING / "assets"
    photo, mask = (assets / "photo.png").read_bytes(), (assets / "mask.png").read_bytes()
    assert Image.open(io.BytesIO(photo)).size == (512, 512)
    assert asset_problems(photo, mask) == []


def test_a_correct_pair_has_no_problems():
    assert asset_problems(png((64, 64), 128), png((64, 64), fill=0, left=255)) == []


def test_a_size_mismatch_is_reported():
    problems = asset_problems(png((64, 64), 128), png((32, 32), fill=0, left=255))
    assert problems == ["the mask and the photo differ in size"]


def test_a_mirrored_mask_is_reported():
    problems = asset_problems(png((64, 64), 128), png((64, 64), fill=255, left=0))
    assert len(problems) == 1 and "edit the left half" in problems[0]
