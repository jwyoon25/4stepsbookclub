"""The Sheet's own contract, restated in Python because it is written elsewhere.

A run of this engine is worth nothing until its rows are in the workbook's
Google Sheet, and that Sheet already has a contract: `sheet-contract.mjs` says
what the Vocabulary tab's columns are called and in what order, and
`lesson.schema.json` says how long each field may be. Both are authoritative and
neither can be imported from Python, so this module holds a copy.

A copy that nothing checks is a copy that drifts, and the way it would be
discovered is a tutor pasting a run into the Sheet and being told column 5 must
be named "Korean meaning". So the paths to both originals are constants here and
a test opens them and asserts these values still agree. Nothing at runtime reads
those files: the engine has to export correctly on a machine that has the Python
package and no monorepo checkout.

The length limits are here rather than left to the builder for the same reason.
The builder does enforce them — and it enforces them after the paste, when the
person holding the error is the tutor and not the operator who ran the engine.
"""

from __future__ import annotations

from pathlib import Path

# This file is at <monorepo>/bookengine/src/bookengine/export/, so the engine's
# own root is three levels up and the monorepo is one above that.
ENGINE_ROOT = Path(__file__).resolve().parents[3]
MONOREPO_ROOT = ENGINE_ROOT.parent

# The two originals these constants mirror. Only the test reads them.
SHEET_CONTRACT_PATH = (
    MONOREPO_ROOT / "workbooks" / "builder" / "browser" / "sheet-contract.mjs"
)
LESSON_SCHEMA_PATH = MONOREPO_ROOT / "workbooks" / "schema" / "lesson.schema.json"

VOCABULARY_SHEET_NAME = "Vocabulary"

# Mirrors `SHEET_HEADERS.Vocabulary` in sheet-contract.mjs — the wording and the
# order both. `requireGrid` there compares the header row string for string, so
# a heading reworded here is a refused import rather than a quiet column shift.
VOCABULARY_COLUMNS: tuple[str, ...] = (
    "Status",
    "Lesson number",
    "Order",
    "Vocabulary word",
    "Korean meaning",
    "English definition",
    "Excerpt from the book",
    "Excerpt context",
    "Chapter reference (optional)",
)

# Mirrors `HEADER_ROW` and `FIRST_DATA_ROW` in sheet-contract.mjs. Rows go under
# the headings, so "paste at A5" is derived from the contract rather than
# remembered — and so is the export being headerless, since row 4 already holds
# the headings and anything pasted at A5 is read as a vocabulary entry.
HEADER_ROW = 4
FIRST_DATA_ROW = 5
PASTE_TARGET = f"A{FIRST_DATA_ROW}"

# Mirrors `$defs.vocabularyEntry.required` in lesson.schema.json. These are the
# fields `parseVocabularyGrid` reads with `{ required: true }`; a blank one is a
# refused workbook, not a thinner page.
VOCABULARY_REQUIRED_FIELDS: tuple[str, ...] = (
    "term",
    "koreanMeaning",
    "definition",
    "bookExcerpt",
    "excerptContext",
)

# Mirrors the `maxLength` of each property in `$defs.vocabularyEntry`. The
# excerpt limit is the same 600 that `ExcerptConfig.max_characters` is capped
# at, and for the same reason: generating past it produces a row the builder
# rejects.
VOCABULARY_FIELD_LIMITS: dict[str, int] = {
    "term": 60,
    "koreanMeaning": 100,
    "definition": 600,
    "bookExcerpt": 600,
    "excerptContext": 700,
    "chapterReference": 80,
}

# Which schema field each column carries. The first three columns are the
# spreadsheet's own bookkeeping: `parseVocabularyGrid` uses the lesson number
# and the order to place the entry, treats Status as a note between people, and
# none of the three reaches the content JSON, so none of them has a limit.
VOCABULARY_COLUMN_FIELDS: dict[str, str | None] = {
    "Status": None,
    "Lesson number": None,
    "Order": None,
    "Vocabulary word": "term",
    "Korean meaning": "koreanMeaning",
    "English definition": "definition",
    "Excerpt from the book": "bookExcerpt",
    "Excerpt context": "excerptContext",
    "Chapter reference (optional)": "chapterReference",
}
