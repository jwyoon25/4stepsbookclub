"""The last mile: a verified run turned into files the workbook already accepts.

The engine's work is not done when a word is proved. It is done when a tutor has
pasted a block into the Vocabulary tab and the builder has taken it. Everything
in this package serves that: the Sheet's contract mirrored so the columns cannot
drift, the paste block itself, and the two artifacts that let anyone ask later
where a row came from.
"""

from __future__ import annotations

from .artifacts import build_audit_summary, write_audit_json, write_vocabulary_json
from .tsv import exportable_items, render_tsv, vocabulary_rows, write_tsv
from .workbook_contract import (
    FIRST_DATA_ROW,
    HEADER_ROW,
    LESSON_SCHEMA_PATH,
    PASTE_TARGET,
    SHEET_CONTRACT_PATH,
    VOCABULARY_COLUMN_FIELDS,
    VOCABULARY_COLUMNS,
    VOCABULARY_FIELD_LIMITS,
    VOCABULARY_REQUIRED_FIELDS,
    VOCABULARY_SHEET_NAME,
)

__all__ = [
    "FIRST_DATA_ROW",
    "HEADER_ROW",
    "LESSON_SCHEMA_PATH",
    "PASTE_TARGET",
    "SHEET_CONTRACT_PATH",
    "VOCABULARY_COLUMNS",
    "VOCABULARY_COLUMN_FIELDS",
    "VOCABULARY_FIELD_LIMITS",
    "VOCABULARY_REQUIRED_FIELDS",
    "VOCABULARY_SHEET_NAME",
    "build_audit_summary",
    "exportable_items",
    "render_tsv",
    "vocabulary_rows",
    "write_audit_json",
    "write_tsv",
    "write_vocabulary_json",
]
