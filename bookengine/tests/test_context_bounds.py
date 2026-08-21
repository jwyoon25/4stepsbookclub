"""How much of a book one request may carry, and what happens when a book lies.

Paragraph assembly rebuilds paragraphs from positioned lines. It is good at it
for books laid out the way books usually are, and there is no guarantee about
the others: a PDF whose page breaks it cannot see will merge blocks a reader
sees as separate, and a "paragraph" becomes six pages of a copyrighted novel.

Two things follow, and both are here. The window that goes to a model is
bounded whatever the paragraph map says, so a badly segmented book cannot make
a definition request post six pages to a third party. And ingestion says so,
because a wrong paragraph map is worth knowing about even when nothing is
leaking.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bookengine.source.excerpt import ExcerptLocator
from bookengine.source.ingest import (
    INGESTION_REVIEW_REQUIRED,
    SUSPICIOUS_PARAGRAPH_CHARACTERS,
    ingest_book,
)
from bookengine.source.search import (
    CONTEXT_CHARACTER_LIMIT,
    ELISION,
    ContextWindow,
    context_for_locator,
)

# The excerpt, in the middle of a paragraph far too big to send whole.
NEEDLE = "the tally scratched into the beam above her head"


def filler(word: str, size: int) -> str:
    """`size` characters of word-shaped prose.

    Word-shaped matters: the trimmer cuts at spaces so that a window never ends
    mid-word, and padding with one enormous unbroken run would exercise a path
    no book produces.
    """
    return (f"{word} " * (size // (len(word) + 1) + 1))[:size].strip()


def window(before: int, passage: int, after: int, focus_at: int) -> ContextWindow:
    """A window with a needle at a known offset inside an oversized passage."""
    opening = filler("before", focus_at)
    closing = filler("after", max(0, passage - focus_at - len(NEEDLE)))
    body = f"{opening}{NEEDLE}{closing}"
    return ContextWindow(
        chapter=1,
        page=1,
        before=filler("earlier", before),
        passage=body,
        after=filler("later", after),
        focus=(len(opening), len(opening) + len(NEEDLE)),
    )


# --- the bound -------------------------------------------------------------


@pytest.mark.parametrize("passage_size", [100, 1_000, 5_000, 60_000])
def test_the_window_stays_bounded_however_large_the_paragraph_is(passage_size):
    """A merged six-page paragraph must not become a six-page request."""
    block = window(4_000, passage_size, 4_000, focus_at=passage_size // 2)
    rendered = block.as_prompt_block()

    # The labels and elision markers are a fixed overhead on top of the budget.
    assert len(rendered) < CONTEXT_CHARACTER_LIMIT + 300


def test_the_default_is_bounded_so_a_caller_cannot_forget():
    """There is no unbounded call to make: `limit` has a default."""
    huge = window(50_000, 50_000, 50_000, focus_at=25_000)

    assert len(huge.as_prompt_block()) < CONTEXT_CHARACTER_LIMIT + 300


def test_the_excerpt_survives_a_budget_that_cannot_fit_its_paragraph():
    """A window that dropped the passage would be worse than no window.

    A model shown only the surrounding prose would answer from it and look as
    though it had read the excerpt.
    """
    rendered = window(0, 40_000, 0, focus_at=20_000).as_prompt_block()

    assert NEEDLE in rendered


def test_a_trimmed_passage_says_it_was_trimmed():
    rendered = window(0, 40_000, 0, focus_at=20_000).as_prompt_block()

    assert rendered.count(ELISION) == 2


def test_a_trimmed_passage_is_still_the_books_own_characters():
    """Nothing is paraphrased or summarised to fit; it is cut."""
    block = window(0, 40_000, 0, focus_at=20_000)
    rendered = block.as_prompt_block()

    for piece in rendered.split(ELISION):
        stripped = piece.strip().removeprefix("[paragraph containing the excerpt]")
        if stripped.strip():
            assert stripped.strip() in block.passage


def test_an_ordinary_paragraph_is_not_trimmed_at_all():
    """The bound is for the pathological case and must not cost the normal one."""
    ordinary = window(300, 600, 300, focus_at=200)
    rendered = ordinary.as_prompt_block()

    assert ELISION not in rendered
    assert ordinary.passage in rendered
    assert ordinary.before in rendered
    assert ordinary.after in rendered


def test_the_neighbours_are_dropped_before_the_passage_is_touched():
    """They are the part furthest from what is being judged."""
    rendered = window(20_000, 1_700, 20_000, focus_at=800).as_prompt_block()

    assert NEEDLE in rendered
    assert len(rendered) < CONTEXT_CHARACTER_LIMIT + 300
    # The passage survived whole; the neighbours paid for it.
    assert rendered.count(ELISION) == 2


def test_the_focus_stays_centred_rather_than_the_paragraph_s_opening():
    """Otherwise a bounded window is a window onto the wrong sentence."""
    rendered = window(0, 40_000, 0, focus_at=30_000).as_prompt_block()

    assert NEEDLE in rendered
    # The prose kept is the prose either side of the needle, not the
    # paragraph's opening 30,000 characters earlier.
    kept = rendered.split(ELISION)[1]
    assert "before" in kept and "after" in kept


# --- both real callers go through it ---------------------------------------


def test_every_window_the_engine_builds_is_bounded(document):
    """Whatever the book, whatever the excerpt, over the whole fixture novel."""
    for chapter in document.chapters:
        for paragraph in chapter.paragraphs:
            locator = ExcerptLocator(
                chapter=chapter.number,
                char_start=paragraph.char_start,
                char_end=min(paragraph.char_start + 200, paragraph.char_end),
            )
            block = context_for_locator(document, locator).as_prompt_block()
            assert len(block) < CONTEXT_CHARACTER_LIMIT + 300


def test_the_generator_and_the_auditor_are_shown_the_same_window(document):
    """The audit prompt tells the auditor the entry was written from these.

    Two window functions with different focuses would make that a lie, and the
    auditor would be checking a claim against prose the writer never saw.
    """
    from bookengine.config import ExcerptConfig
    from bookengine.source.search import find_occurrences
    from bookengine.vocabulary.audit import _render_source
    from bookengine.vocabulary.entries import CONTEXT_PARAGRAPHS
    from bookengine.vocabulary.models import VocabularyItem
    from bookengine.vocabulary.quotes import build_excerpt

    occurrence = find_occurrences(document, "predicament")[0]
    candidate = build_excerpt(document, occurrence, ExcerptConfig())
    item = VocabularyItem(lesson=1, term="predicament", normalized_term="predicament")
    item.locator, item.excerpt = candidate.locator, candidate.text

    generator_sees = context_for_locator(
        document,
        item.locator,
        paragraphs_before=CONTEXT_PARAGRAPHS,
        paragraphs_after=CONTEXT_PARAGRAPHS,
    ).as_prompt_block()

    assert _render_source(item, document) == generator_sees


# --- and the book that would have caused it is flagged ---------------------


@pytest.fixture(scope="module")
def merged_paragraph_book(tmp_path_factory) -> Path:
    """A chapter whose prose is one block far larger than any paragraph."""
    from fixtures.prose import chapter_specs
    from fixtures.synthetic_book import ChapterSpec, render_book

    chapters = chapter_specs(6)
    chapters[2] = ChapterSpec(
        number=3,
        paragraphs=[
            " ".join(["The corridor ran on and on without any windows in it."] * 200)
        ],
    )
    path = tmp_path_factory.mktemp("merged") / "merged.pdf"
    render_book(path, chapters=chapters)
    return path


def test_a_merged_paragraph_makes_ingestion_ask_for_review(merged_paragraph_book):
    report = ingest_book(merged_paragraph_book, cache=None, use_cache=False)

    assert report.status == INGESTION_REVIEW_REQUIRED
    assert any("Paragraph assembly has merged" in c for c in report.concerns)
    assert any(f"{SUSPICIOUS_PARAGRAPH_CHARACTERS:,}" in c for c in report.concerns)


def test_an_ordinary_book_is_not_flagged_for_it(document):
    """The threshold has to sit above real prose or it says nothing."""
    largest = max(
        paragraph.char_end - paragraph.char_start
        for chapter in document.chapters
        for paragraph in chapter.paragraphs
    )

    assert largest < SUSPICIOUS_PARAGRAPH_CHARACTERS


def test_the_bound_holds_on_that_book_anyway(merged_paragraph_book):
    """The flag is advisory; the bound is not, and does not depend on it."""
    document = ingest_book(merged_paragraph_book, cache=None, use_cache=False).document
    chapter = document.chapter(3)
    biggest = max(
        chapter.paragraphs, key=lambda p: p.char_end - p.char_start
    )
    assert biggest.char_end - biggest.char_start > SUSPICIOUS_PARAGRAPH_CHARACTERS

    locator = ExcerptLocator(
        chapter=3,
        char_start=biggest.char_start + 3_000,
        char_end=biggest.char_start + 3_200,
    )
    block = context_for_locator(document, locator).as_prompt_block()

    assert len(block) < CONTEXT_CHARACTER_LIMIT + 300
