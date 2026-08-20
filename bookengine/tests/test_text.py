"""The comparison rules, which everything else depends on being one rule."""

from __future__ import annotations

import random
import unicodedata

import pytest

from bookengine.source.text import (
    contains_whole_word,
    flatten_for_cell,
    normalize_for_matching,
    normalize_term,
    normalize_with_offsets,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("“quoted”", '"quoted"'),
        ("it’s", "it's"),
        ("dash—here", "dash-here"),
        ("wait…", "wait..."),
        ("ﬁrst ﬂight", "first flight"),
        ("a b", "a b"),
        ("  spaced   out  ", "spaced out"),
        ("line\nbreak", "line break"),
    ],
)
def test_matching_form_folds_what_a_pdf_spells_differently(raw, expected):
    assert normalize_for_matching(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  “Lurch,” ", "lurch"),
        ("Predicament.", "predicament"),
        ("self-aware", "self-aware"),
        ("don’t", "don't"),
    ],
)
def test_term_form_drops_case_and_edge_punctuation_only(raw, expected):
    assert normalize_term(raw) == expected


def test_whole_word_matching_does_not_leak_into_neighbours():
    assert contains_whole_word("a sickening lurch that", "Lurch")
    assert not contains_whole_word("shuck-face", "shuck")
    assert not contains_whole_word("running fast", "run")
    assert not contains_whole_word("Thomas’s mind", "Thomas")


def test_cell_flattening_removes_what_would_break_a_row():
    assert flatten_for_cell("a\tb\nc\r\nd") == "a b c d"


def test_the_two_normalizers_agree_on_random_input():
    """`normalize_with_offsets` is a second implementation of one definition.

    It is only useful while it agrees with the first, so the agreement is
    asserted over generated input rather than assumed from the code.
    """
    alphabet = list("abc “”’—… ​ \n\tﬁ.,'\"")
    generator = random.Random(20260820)
    for _ in range(2000):
        length = generator.randint(0, 60)
        raw = unicodedata.normalize(
            "NFC", "".join(generator.choice(alphabet) for _ in range(length))
        )
        normalized, starts, ends = normalize_with_offsets(raw)
        assert normalized == normalize_for_matching(raw)
        assert len(starts) == len(ends) == len(normalized)
        for index in range(len(normalized)):
            assert 0 <= starts[index] <= ends[index] <= len(raw)


def test_offsets_map_a_match_back_to_the_original_characters():
    raw = "“Somebody up there,” she called, and her voice came back."
    normalized, starts, ends = normalize_with_offsets(raw)
    start = normalized.index("Somebody")
    end = start + len("Somebody up there")
    assert raw[starts[start] : ends[end - 1]] == "Somebody up there"
