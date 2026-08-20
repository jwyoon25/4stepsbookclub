"""The one definition of how book text is compared.

Extracted PDF text and text that came back through an LLM prompt are never
byte-identical: a PDF hands over U+2019 where a prompt echoes an ASCII
apostrophe, a line break becomes a space, a soft hyphen survives a round trip.
Every comparison in this engine runs through :func:`normalize_for_matching`,
and every comparison runs through *the same one*, so that "this quotation is in
the book" means one thing everywhere.

Normalization is for comparing only. Text that reaches a workbook is always a
raw slice of the book's canonical text, carrying the book's own punctuation.
Nothing in this module rewrites what gets exported.

The substitutions are deliberately narrow. Each exists because a PDF and a
keyboard spell one character two ways; none of them changes which words are
present. Case folding and punctuation stripping are *not* part of it — those
belong to :func:`normalize_term`, which compares vocabulary words rather than
sentences.
"""

from __future__ import annotations

import re
import unicodedata

# Characters a PDF and a keyboard disagree about, mapped to one spelling.
_CHARACTER_FOLDS = {
    # Apostrophes and single quotes.
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "′": "'",
    "´": "'",
    "`": "'",
    # Double quotes.
    "“": '"',
    "”": '"',
    "„": '"',
    "‟": '"',
    "″": '"',
    # Dashes and hyphens.
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "―": "-",
    "−": "-",
    # Ellipsis.
    "…": "...",
    # Ligatures a PDF font sometimes hands back whole.
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
}

_FOLD_TABLE = str.maketrans(_CHARACTER_FOLDS)

# Characters that occupy no width and must not affect a match: zero-width
# space/non-joiner/joiner, word joiner, byte-order mark, and the soft hyphen a
# justified PDF leaves behind.
_INVISIBLE = re.compile("[­​‌‍⁠﻿]")

# Every space-like character, including the ones `str.split()` misses.
_WHITESPACE = re.compile(
    "[\\s   -     　]+"
)

# A word boundary defined for this corpus rather than borrowed from `\b`.
# `\b` would let `shuck` match inside `shuck-face` and would treat a possessive
# as a separate word; the workbook cares about neither of those as separate
# vocabulary. `\w` covers Unicode letters and digits for `str` patterns.
_BOUNDARY_LEFT = "(?<![\\w'’-])"
_BOUNDARY_RIGHT = "(?![\\w'’-])"


def fold_characters(value: str) -> str:
    """Fold the characters a PDF spells differently from a keyboard.

    Kept separate from whitespace handling so a caller that needs to preserve
    line structure — the paragraph assembler, for one — can fold characters
    without flattening the text.
    """
    return _INVISIBLE.sub("", unicodedata.normalize("NFC", value)).translate(
        _FOLD_TABLE
    )


def collapse_whitespace(value: str) -> str:
    """Collapse every run of whitespace to one space and trim the ends."""
    return _WHITESPACE.sub(" ", value).strip()


def normalize_for_matching(value: str) -> str:
    """The comparison form of a passage.

    Two strings that normalize to the same value contain the same words in the
    same order, differing only in how the PDF and the caller spelled quotation
    marks, dashes, ligatures, and whitespace.
    """
    return collapse_whitespace(fold_characters(value))


def normalize_term(value: str) -> str:
    """The comparison form of a vocabulary word.

    Case and surrounding punctuation are not part of a word's identity, so
    ``"Lurch,"`` and ``lurch`` are one entry. Internal hyphens and apostrophes
    are kept, because ``self-aware`` and ``selfaware`` are not one word.
    """
    folded = collapse_whitespace(fold_characters(value)).lower()
    return folded.strip("\"'()[]{}.,;:!?… \t—-")


def flatten_for_cell(value: str) -> str:
    """Make a value safe to occupy one spreadsheet cell.

    A tab ends a cell and a newline ends a row, so a value carrying either
    would silently shift every column to its right. Both become one space.
    This runs at export time only: the verifier compares against the
    unflattened text, and :func:`normalize_for_matching` treats the two as
    equal anyway.
    """
    return collapse_whitespace(re.sub("[\t\r\n\v\f]+", " ", value))


def whole_word_pattern(term: str, flags: int = re.IGNORECASE) -> re.Pattern[str]:
    """Compile a pattern that finds one word as a whole word.

    The term is normalized first, so the pattern is built from the same
    spelling the corpus is compared in.
    """
    escaped = re.escape(normalize_term(term))
    return re.compile(f"{_BOUNDARY_LEFT}{escaped}{_BOUNDARY_RIGHT}", flags)


def contains_whole_word(passage: str, term: str) -> bool:
    """Whether one word occurs as a whole word inside a passage.

    Both sides are normalized first, so this answers the question the workbook
    actually asks — does the student see this word in this sentence — rather
    than a question about how the PDF encoded a dash.
    """
    normalized = normalize_term(term)
    if not normalized:
        return False
    haystack = normalize_for_matching(passage)
    return whole_word_pattern(normalized).search(haystack) is not None


def is_space(character: str) -> bool:
    """Whether one character is whitespace by this module's definition."""
    return _WHITESPACE.fullmatch(character) is not None


def normalize_with_offsets(raw: str) -> tuple[str, list[int], list[int]]:
    """Normalize a passage while remembering where every character came from.

    Searching has to happen in comparison form — otherwise a word is missed
    because the PDF spelled a quotation mark unusually — but a quotation has to
    be cut from the raw text, at raw offsets, or it is not the book's text any
    more. This returns both: the normalized string, and for each of its
    characters the half-open span of `raw` it came from.

    A match at normalized ``[a, b)`` is therefore at raw
    ``[starts[a], ends[b - 1])``.

    The result satisfies ``normalized == normalize_for_matching(raw)`` for any
    NFC-normalized input, which is what the canonical chapter text is. That
    equality is asserted in the tests rather than assumed, because these are
    two implementations of one definition and they are only useful while they
    agree.
    """
    characters: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    pending_space = False

    for index, character in enumerate(raw):
        if _INVISIBLE.fullmatch(character):
            continue

        if is_space(character):
            pending_space = bool(characters)
            continue

        if pending_space:
            characters.append(" ")
            starts.append(index)
            ends.append(index)
            pending_space = False

        for produced in _CHARACTER_FOLDS.get(character, character):
            characters.append(produced)
            starts.append(index)
            ends.append(index + 1)

    return "".join(characters), starts, ends
