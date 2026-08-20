"""Quotations: what a locator proves, and what it refuses to."""

from __future__ import annotations

import pytest

from bookengine.config import ExcerptConfig
from bookengine.source.excerpt import (
    ExcerptError,
    ExcerptLocator,
    excerpt_for_cell,
    locator_from_sentences,
    resolve_excerpt,
    verify_excerpt,
)
from bookengine.source.search import find_occurrences
from bookengine.vocabulary.quotes import choose_excerpt, excerpt_candidates

# A real sentence from a different book. It is the shape of thing a model
# produces from memory, which is exactly what must never verify.
FABRICATED = (
    "At that moment, Thomas realized with a sickening lurch that he had no "
    "idea how old he was."
)


def locator_for(document, term="predicament"):
    occurrence = find_occurrences(document, term)[0]
    return locator_from_sentences(
        document, occurrence.chapter, [occurrence.sentence_id]
    )


def test_a_real_locator_resolves_and_verifies(document):
    locator = locator_for(document)
    text = excerpt_for_cell(document, locator)
    verification = verify_excerpt(document, locator, text, term="predicament")

    assert verification.ok
    assert "predicament" in text.lower()


def test_a_fabricated_quotation_cannot_verify(document):
    locator = locator_for(document)
    verification = verify_excerpt(document, locator, FABRICATED, term="lurch")

    assert not verification.ok
    assert verification.checks["slice_matches"] is False
    assert verification.checks["present_in_chapter"] is False


def test_a_corrupted_locator_is_caught_by_the_independent_check(document):
    """The two checks are only worth having because they can disagree."""
    real = locator_for(document)
    text = excerpt_for_cell(document, real)
    moved = ExcerptLocator(chapter=real.chapter, char_start=10, char_end=90)

    verification = verify_excerpt(document, moved, text)
    assert not verification.ok
    assert verification.checks["slice_matches"] is False
    # The words are still the book's, which is what the second check tests.
    assert verification.checks["present_in_chapter"] is True


def test_a_word_missing_from_its_own_excerpt_fails(document):
    locator = locator_for(document)
    text = excerpt_for_cell(document, locator)
    verification = verify_excerpt(document, locator, text, term="unicycle")

    assert not verification.ok
    assert verification.checks["word_in_excerpt"] is False


def test_an_excerpt_may_not_cross_a_paragraph_break(document):
    chapter = document.chapters[0]
    spanning = ExcerptLocator(
        chapter=chapter.number,
        char_start=chapter.paragraphs[0].char_start,
        char_end=chapter.paragraphs[1].char_end,
    )
    with pytest.raises(ExcerptError, match="paragraph"):
        resolve_excerpt(document, spanning)


def test_a_locator_outside_the_chapter_is_refused(document):
    chapter = document.chapters[0]
    with pytest.raises(ExcerptError, match="outside"):
        resolve_excerpt(
            document,
            ExcerptLocator(
                chapter=chapter.number, char_start=0, char_end=len(chapter.text) + 50
            ),
        )


def test_the_chapter_reference_comes_from_the_locator(document):
    locator = locator_for(document)
    assert locator.chapter_reference == f"Chapter {locator.chapter}"


def test_the_shortlist_shown_to_a_model_carries_no_locations(document):
    from bookengine.vocabulary.quotes import render_shortlist

    candidates = excerpt_candidates(
        document, "predicament", range(1, 13), ExcerptConfig()
    )
    listing = render_shortlist(candidates)

    assert "Chapter" not in listing
    assert "char_start" not in listing


def test_a_model_index_outside_the_shortlist_still_yields_a_real_quote(document):
    config = ExcerptConfig()
    for bogus in (99, -1, "two", None):
        chosen = choose_excerpt(
            document,
            "predicament",
            range(1, 13),
            config,
            chooser=lambda *_, answer=bogus: answer,
        )
        assert chosen is not None
        assert verify_excerpt(document, chosen.locator, chosen.text).ok


def test_a_chooser_that_raises_does_not_lose_the_word(document):
    def explode(term, candidates):
        raise RuntimeError("the endpoint fell over")

    chosen = choose_excerpt(
        document, "predicament", range(1, 13), ExcerptConfig(), chooser=explode
    )
    assert chosen is not None
    assert verify_excerpt(document, chosen.locator, chosen.text).ok


def test_a_word_with_no_usable_passage_returns_nothing(document):
    assert (
        choose_excerpt(document, "unicycle", range(1, 13), ExcerptConfig()) is None
    )
