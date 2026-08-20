"""Export: the paste block, and the contract it has to keep agreeing with."""

from __future__ import annotations

import json
import re

import pytest

from bookengine.errors import VerificationError
from bookengine.export import render_tsv, write_tsv
from bookengine.export.workbook_contract import (
    FIRST_DATA_ROW,
    HEADER_ROW,
    LESSON_SCHEMA_PATH,
    SHEET_CONTRACT_PATH,
    VOCABULARY_COLUMNS,
    VOCABULARY_FIELD_LIMITS,
    VOCABULARY_REQUIRED_FIELDS,
)
from bookengine.source.excerpt import ExcerptLocator, ExcerptVerification
from bookengine.vocabulary.models import AuditVerdict, Status, VocabularyItem


def ready_item(**overrides) -> VocabularyItem:
    """One item that has legitimately reached READY."""
    item = VocabularyItem(lesson=1, term="predicament", normalized_term="predicament")
    item.locator = ExcerptLocator(chapter=2, char_start=0, char_end=10)
    item.excerpt = "They gave her a bed in the long hut."
    item.definition = "a difficult or unpleasant situation."
    item.korean_meaning = "곤경, 궁지"
    item.excerpt_context = "Mara is left alone to work out where she is."
    item.order = 1
    item.audit = AuditVerdict(
        verdict="PASS",
        difficulty="APPROPRIATE",
        definition_accuracy="ACCURATE",
        korean_accuracy="ACCURATE",
        context_accuracy="ACCURATE",
        excerpt_fit="GOOD",
    )
    for key, value in overrides.items():
        setattr(item, key, value)

    item.transition(Status.SOURCE_VERIFIED, "test")
    item.transition(Status.GENERATED, "test")
    item.transition(Status.AUDIT_PENDING, "test")
    item.mark_ready(
        ExcerptVerification(ok=True, checks={"slice_matches": True}), "test"
    )
    return item


# --- the drift guards ------------------------------------------------------


def test_the_column_list_still_matches_the_sheet_contract():
    """These constants mirror a JavaScript file. This is what notices drift."""
    source = SHEET_CONTRACT_PATH.read_text(encoding="utf-8")
    block = re.search(r"Vocabulary:\s*\[(.*?)\]", source, re.DOTALL)
    assert block, f"No Vocabulary headers found in {SHEET_CONTRACT_PATH}"
    assert tuple(re.findall(r'"([^"]+)"', block.group(1))) == VOCABULARY_COLUMNS


def test_the_paste_row_numbers_still_match_the_sheet_contract():
    source = SHEET_CONTRACT_PATH.read_text(encoding="utf-8")
    assert int(re.search(r"HEADER_ROW = (\d+)", source).group(1)) == HEADER_ROW
    assert int(re.search(r"FIRST_DATA_ROW = (\d+)", source).group(1)) == FIRST_DATA_ROW


def test_the_field_limits_still_match_the_workbook_content_schema():
    entry = json.loads(LESSON_SCHEMA_PATH.read_text(encoding="utf-8"))["$defs"][
        "vocabularyEntry"
    ]
    assert tuple(entry["required"]) == VOCABULARY_REQUIRED_FIELDS
    assert {
        name: rules["maxLength"]
        for name, rules in entry["properties"].items()
        if "maxLength" in rules
    } == VOCABULARY_FIELD_LIMITS


# --- the paste block -------------------------------------------------------


def test_the_header_row_is_the_sheet_s_own_wording():
    text = render_tsv([ready_item()])
    assert text.splitlines()[0].split("\t") == list(VOCABULARY_COLUMNS)


def test_nothing_below_ready_is_exported():
    ready = ready_item()
    rejected = VocabularyItem(lesson=1, term="wall", normalized_term="wall")
    rejected.fail("too easy")

    text = render_tsv([ready, rejected])
    assert len(text.splitlines()) == 2
    assert "wall" not in text


def test_a_tab_or_newline_in_a_cell_cannot_shift_the_columns():
    """The failure this guards against is silent and ruins every later column."""
    item = ready_item()
    item.excerpt_context = "She waits.\tThen\nshe moves."

    rows = [line.split("\t") for line in render_tsv([item]).splitlines()]
    assert all(len(row) == len(VOCABULARY_COLUMNS) for row in rows)
    assert "She waits. Then she moves." in rows[1]


def test_korean_and_the_book_s_punctuation_survive_the_file(tmp_path):
    item = ready_item()
    item.excerpt = "“They gave her a bed,” he said—kindly."
    path = write_tsv([item], tmp_path / "vocabulary.tsv")

    text = path.read_text(encoding="utf-8")
    assert "곤경, 궁지" in text
    assert "“They gave her a bed,”" in text
    assert "—" in text
    assert not text.startswith("﻿")


def test_a_cell_over_the_workbook_s_limit_fails_here_not_at_the_paste():
    item = ready_item()
    item.definition = "x" * (VOCABULARY_FIELD_LIMITS["definition"] + 1)

    with pytest.raises(VerificationError) as failure:
        render_tsv([item])
    assert "definition" in str(failure.value)


def test_rows_are_ordered_by_lesson_then_order():
    first = ready_item()
    second = ready_item(term="monotonous", normalized_term="monotonous")
    second.lesson, second.order = 2, 1
    third = ready_item(term="articulate", normalized_term="articulate")
    third.order = 2

    text = render_tsv([second, third, first])
    rows = [line.split("\t") for line in text.splitlines()]
    assert [row[3] for row in rows[1:]] == ["predicament", "articulate", "monotonous"]
