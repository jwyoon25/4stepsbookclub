"""What a quotation is, and how it is proved.

An excerpt is not a string. It is a locator — a chapter and a pair of character
offsets — and the text is whatever slicing the chapter at those offsets returns.
That is the single design decision this engine is built around: a model can
propose which passage to use, but it has no field in which to hand over the
words, so a fabricated quotation has no route to a workbook. It is not caught;
it is unrepresentable.

Verification then re-derives the text two independent ways. The first re-cuts
the slice and compares. The second ignores the offsets completely and asks
whether the exported words appear anywhere in the chapter at all. They can only
disagree if something between here and export corrupted an offset, which is
exactly the case a single check would miss.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .document import PARAGRAPH_SEPARATOR, BookDocument
from .text import (
    contains_whole_word,
    flatten_for_cell,
    normalize_for_matching,
)


@dataclass(frozen=True, slots=True)
class ExcerptLocator:
    """Where in the book a quotation is, with no copy of its words."""

    chapter: int
    char_start: int
    char_end: int
    sentence_ids: tuple[str, ...] = ()
    page_start: int = 0
    page_end: int = 0

    @property
    def chapter_reference(self) -> str:
        """The workbook's chapter citation, derived from the map, never claimed.

        This is the only place a chapter reference is produced. A model saying
        "this is from Chapter 14" carries no weight anywhere in the engine.
        """
        return f"Chapter {self.chapter}"

    def as_dict(self) -> dict:
        return {
            "chapter": self.chapter,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "sentence_ids": list(self.sentence_ids),
            "page_start": self.page_start,
            "page_end": self.page_end,
        }


@dataclass(slots=True)
class ExcerptVerification:
    """The result of proving one quotation, check by check."""

    ok: bool
    checks: dict[str, bool] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def failed(self) -> list[str]:
        return [name for name, passed in self.checks.items() if not passed]


class ExcerptError(Exception):
    """A locator that does not describe a quotable passage."""


def resolve_excerpt(document: BookDocument, locator: ExcerptLocator) -> str:
    """Produce the quotation's text by cutting the book at the locator.

    Every excerpt that reaches a workbook comes through this function. There is
    deliberately no other way to obtain one.
    """
    chapter = document.chapter(locator.chapter)

    if not 0 <= locator.char_start < locator.char_end <= len(chapter.text):
        raise ExcerptError(
            f"Locator [{locator.char_start}, {locator.char_end}) is outside "
            f"chapter {locator.chapter}, which is {len(chapter.text)} characters."
        )

    text = chapter.slice(locator.char_start, locator.char_end)

    if PARAGRAPH_SEPARATOR in text:
        raise ExcerptError(
            f"The excerpt for chapter {locator.chapter} crosses a paragraph "
            "boundary. A workbook quotation comes from one passage."
        )

    return text


def excerpt_for_cell(document: BookDocument, locator: ExcerptLocator) -> str:
    """The excerpt as it will occupy one spreadsheet cell."""
    return flatten_for_cell(resolve_excerpt(document, locator))


def verify_excerpt(
    document: BookDocument,
    locator: ExcerptLocator,
    exported: str,
    *,
    term: str | None = None,
) -> ExcerptVerification:
    """Prove that an exported quotation is the book's own words.

    Passing every check here is a precondition for `READY`. The checks are
    deliberately redundant: `slice_matches` trusts the offsets, and
    `present_in_chapter` does not, so the two together survive a corrupted
    locator as well as a substituted string.
    """
    verification = ExcerptVerification(ok=False)

    try:
        raw = resolve_excerpt(document, locator)
    except (ExcerptError, KeyError) as cause:
        verification.checks["locator_resolves"] = False
        verification.reasons.append(str(cause))
        return verification

    verification.checks["locator_resolves"] = True

    verification.checks["slice_matches"] = flatten_for_cell(raw) == exported
    if not verification.checks["slice_matches"]:
        verification.reasons.append(
            "The exported text is not what the book says at this locator. "
            "The excerpt was altered after it was cut from the source."
        )

    chapter = document.chapter(locator.chapter)
    normalized = normalize_for_matching(exported)
    verification.checks["present_in_chapter"] = (
        bool(normalized) and normalized in chapter.normalized
    )
    if not verification.checks["present_in_chapter"]:
        verification.reasons.append(
            f"The exported text does not occur anywhere in chapter "
            f"{locator.chapter}."
        )

    verification.checks["non_empty"] = bool(exported.strip())
    if not verification.checks["non_empty"]:
        verification.reasons.append("The excerpt is empty.")

    if term is not None:
        verification.checks["word_in_excerpt"] = contains_whole_word(exported, term)
        if not verification.checks["word_in_excerpt"]:
            verification.reasons.append(
                f"The word “{term}” does not appear in its own excerpt, so the "
                "passage cannot teach it."
            )

    verification.ok = all(verification.checks.values())
    return verification


def locator_from_sentences(
    document: BookDocument, chapter_number: int, sentence_ids: list[str]
) -> ExcerptLocator:
    """Build a locator spanning a run of consecutive sentences.

    Requiring one paragraph and one chapter is what keeps an excerpt readable:
    a quotation stitched across a scene break is not a passage a student can be
    asked to learn a word from.
    """
    chapter = document.chapter(chapter_number)
    sentences = [chapter.sentence(identifier) for identifier in sentence_ids]
    if not sentences:
        raise ExcerptError("An excerpt needs at least one sentence.")

    paragraphs = {sentence.paragraph_id for sentence in sentences}
    if len(paragraphs) != 1:
        raise ExcerptError(
            "An excerpt must come from one paragraph; these sentences span "
            f"{len(paragraphs)}."
        )

    ordered = sorted(sentences, key=lambda sentence: sentence.char_start)
    return ExcerptLocator(
        chapter=chapter_number,
        char_start=ordered[0].char_start,
        char_end=ordered[-1].char_end,
        sentence_ids=tuple(sentence.id for sentence in ordered),
        page_start=min(sentence.page for sentence in ordered),
        page_end=max(sentence.page for sentence in ordered),
    )
