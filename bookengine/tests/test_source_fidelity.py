"""Whether a quotation is the book's characters, or this engine's.

Extraction is not lossless. A justified page breaks words across lines, and a
book repeats its title and folio on every page in the middle of the text
stream. Both have to be dealt with before the prose reads as prose, and both
change the characters a student is later told the book printed.

So the question these tests ask is not "did the excerpt verify". It will:
verification compares the export against the processed document, and the
processed document is exactly where the damage would be. The question is
whether the processing is one the book itself vouches for.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bookengine.config import ExcerptConfig, JobConfig
from bookengine.source.excerpt import ExcerptLocator, unconfirmed_words
from bookengine.source.ingest import FULL_TEXT_PASS, ingest_book
from bookengine.source.layout import (
    REPAIR_HYPHENATED,
    REPAIR_JOINED,
    REPAIR_UNCERTAIN,
    build_lexicon,
    classify_repair,
)
from bookengine.source.search import find_occurrences
from bookengine.source.text import normalize_term
from bookengine.vocabulary.candidates import Candidate
from bookengine.vocabulary.models import RubricScore
from bookengine.vocabulary.quotes import build_excerpt, excerpt_candidates
from bookengine.vocabulary.verify import verify_item
from conftest import build_job
from fixtures.prose import chapter_specs
from fixtures.synthetic_book import ChapterSpec, render_book

# Long enough that the fixture's layout breaks it across a line, and a word
# whose closed-up spelling is the right reading.
LONG_WORD = "extraordinary"

# A genuine hyphenated compound. Broken at its own hyphen it is
# indistinguishable from a typesetter's break, and closing it up would invent
# a spelling no English book contains.
COMPOUND = "self-conscious"


def paragraph(text: str) -> str:
    """Padding, so a rendered paragraph is long enough to wrap and hyphenate."""
    return text + " " + " ".join(["The corridor ran on without windows."] * 6)


# --- the decision itself ---------------------------------------------------


def test_a_word_the_book_sets_whole_elsewhere_closes_up():
    lexicon = frozenset({LONG_WORD, "corridor"})
    assert classify_repair("extraor-", "dinary", lexicon) == (
        REPAIR_JOINED,
        LONG_WORD,
    )


def test_a_compound_the_book_hyphenates_elsewhere_keeps_its_hyphen():
    """`selfconscious` is not a word, and the book says so by never using it."""
    lexicon = frozenset({COMPOUND, "corridor"})
    assert classify_repair("self-", "conscious", lexicon) == (
        REPAIR_HYPHENATED,
        COMPOUND,
    )


def test_a_break_the_book_settles_neither_way_is_uncertain():
    kind, _ = classify_repair("extraor-", "dinary", frozenset({"corridor"}))
    assert kind == REPAIR_UNCERTAIN


def test_a_book_that_uses_both_spellings_settles_nothing():
    """Both readings attested is no more decidable than neither."""
    kind, _ = classify_repair(
        "self-", "conscious", frozenset({COMPOUND, "selfconscious"})
    )
    assert kind == REPAIR_UNCERTAIN


def test_the_lexicon_is_built_only_from_unbroken_words():
    """A fragment is the question, so it must not also be the answer."""
    from bookengine.source.pdf import TextLine

    def line(text: str) -> TextLine:
        return TextLine(page=1, block=0, text=text, x0=0, y0=0, x1=1, y1=1, size=10)

    lexicon = build_lexicon([line("the extraor-"), line("dinary corridor")])

    assert "extraor-" not in lexicon
    assert "corridor" in lexicon


# --- the same decision, made from a real PDF -------------------------------


@pytest.fixture(scope="module")
def hyphen_book(tmp_path_factory) -> Path:
    """A book that breaks a compound across a line and uses it whole elsewhere.

    Both spellings have to be in the PDF for this to be a test of the lexicon
    rather than of luck: the compound appears whole in chapter 1 and is broken
    across a line in chapter 2, which is exactly the evidence a real novel
    leaves.
    """
    chapters = chapter_specs(4)
    chapters[0].paragraphs.append(
        paragraph(f"She was {COMPOUND} about the sound her boots made.")
    )
    chapters[1].paragraphs.append(
        paragraph(
            f"Being {COMPOUND} in front of them was worse than being afraid, "
            f"and the {LONG_WORD} thing was that nobody noticed."
        )
    )
    chapters[2].paragraphs.append(
        paragraph(f"It was an {LONG_WORD} way to spend a morning.")
    )

    path = tmp_path_factory.mktemp("hyphen") / "hyphenated.pdf"
    render_book(path, chapters=chapters)
    return path


def test_a_genuine_hyphen_survives_ingestion(hyphen_book):
    """The whole point: `self-conscious` does not become `selfconscious`."""
    document = ingest_book(hyphen_book, cache=None, use_cache=False).document
    text = "\n".join(chapter.text for chapter in document.chapters)

    assert "selfconscious" not in text.lower()
    assert COMPOUND in text


def test_a_word_broken_across_a_line_is_findable_again(hyphen_book):
    """The repair still has to do its job, or half the book is unsearchable."""
    document = ingest_book(hyphen_book, cache=None, use_cache=False).document

    assert find_occurrences(document, LONG_WORD)
    assert find_occurrences(document, COMPOUND)


def test_the_report_counts_unconfirmed_repairs_apart_from_the_rest(hyphen_book):
    report = ingest_book(hyphen_book, cache=None, use_cache=False)
    stats = report.document.stats

    assert stats.hyphen_repairs >= stats.hyphen_repairs_uncertain
    assert "unconfirmed" in report.render()


# --- what an unconfirmed repair is allowed to become -----------------------


def uncertain_locator(document) -> tuple[int, ExcerptLocator]:
    """A locator over a paragraph the book could not confirm, if there is one."""
    for chapter in document.chapters:
        for para in chapter.paragraphs:
            if para.uncertain_repair_offsets:
                return chapter.number, ExcerptLocator(
                    chapter=chapter.number,
                    char_start=para.char_start,
                    char_end=para.char_end,
                )
    return 0, None


def test_an_unconfirmed_repair_is_reported_by_the_locator_check(hyphen_book):
    document = ingest_book(hyphen_book, cache=None, use_cache=False).document
    _, locator = uncertain_locator(document)
    if locator is None:
        pytest.skip("this rendering left no unconfirmed repairs")

    assert unconfirmed_words(document, locator)


def test_a_confirmed_passage_reports_nothing_unconfirmed(hyphen_book):
    """The control: the check is not simply saying yes to everything."""
    document = ingest_book(hyphen_book, cache=None, use_cache=False).document
    chapter = document.chapters[0]
    clean = next(
        para for para in chapter.paragraphs if not para.uncertain_repair_offsets
    )

    assert (
        unconfirmed_words(
            document,
            ExcerptLocator(
                chapter=chapter.number,
                char_start=clean.char_start,
                char_end=clean.char_end,
            ),
        )
        == []
    )


def test_no_selected_excerpt_reads_a_word_the_book_did_not_confirm(hyphen_book):
    """Every candidate offered for every word in the book, checked."""
    document = ingest_book(hyphen_book, cache=None, use_cache=False).document
    config = ExcerptConfig()

    for chapter in document.chapters:
        for word in {normalize_term(w) for w in chapter.text.split()}:
            if len(word) < 5:
                continue
            for candidate in excerpt_candidates(
                document, word, [chapter.number], config
            ):
                assert unconfirmed_words(document, candidate.locator) == []


def test_an_occurrence_over_an_unconfirmed_repair_yields_no_excerpt(hyphen_book):
    """Refused under the default; visible, and still unexportable, under `review`.

    Both halves matter. The first is the guarantee. The second is that a book
    hyphenated past usefulness can be looked at rather than only failing — and
    that looking at it is all `review` buys, since the passage still cannot
    reach a student.
    """
    document = ingest_book(hyphen_book, cache=None, use_cache=False).document
    strict = ExcerptConfig()
    permissive = ExcerptConfig(unconfirmed_repairs="review")

    blocked = [
        occurrence
        for chapter in document.chapters
        for word in {normalize_term(w) for w in chapter.text.split() if len(w) > 6}
        for occurrence in find_occurrences(document, word, chapters=[chapter.number])
        if build_excerpt(document, occurrence, permissive) is not None
        and unconfirmed_words(
            document, build_excerpt(document, occurrence, permissive).locator
        )
    ]
    if not blocked:
        pytest.skip("this rendering left no unconfirmed repairs")

    assert all(
        build_excerpt(document, occurrence, strict) is None
        for occurrence in blocked
    )
    # And what `review` returns is marked as something that cannot be exported.
    assert all(
        not build_excerpt(document, occurrence, permissive).is_quotable
        for occurrence in blocked
    )


def test_final_verification_refuses_an_unconfirmed_excerpt(hyphen_book, tmp_path):
    """Defence in depth: even handed a ready item, the last gate says no."""
    from bookengine.vocabulary.models import Status, VocabularyItem

    document = ingest_book(hyphen_book, cache=None, use_cache=False).document
    number, locator = uncertain_locator(document)
    if locator is None:
        pytest.skip("this rendering left no unconfirmed repairs")

    job: JobConfig = build_job(
        hyphen_book,
        tmp_path / "out",
        lessons=[{"lesson": 1, "start_chapter": 1, "end_chapter": 4}],
        excerpt={"max_characters": 600, "min_characters": 10},
    )
    chapter = document.chapter(number)
    item = VocabularyItem(lesson=1, term="corridor", normalized_term="corridor")
    item.locator = locator
    item.excerpt = chapter.slice(locator.char_start, locator.char_end)
    item.definition = "a passage"
    item.korean_meaning = "복도"
    item.excerpt_context = "Mara walks."
    item.status = Status.AUDIT_PENDING

    verification = verify_item(document, job, item)

    assert verification.checks["excerpt_is_confirmed_text"] is False
    assert not verification.ok


# --- page furniture --------------------------------------------------------


RUNNING_HEAD = "THE HOLLOW ROAD"


def furniture_in(document) -> list[str]:
    """Any chapter text that reads as a running head or a bare folio."""
    found: list[str] = []
    for chapter in document.chapters:
        for line in chapter.text.split("\n"):
            for word in line.split():
                if word.strip(".,;:!?\"'").isdigit() and len(word) <= 3:
                    found.append(f"chapter {chapter.number}: folio {word!r}")
        if RUNNING_HEAD.lower() in chapter.text.lower():
            found.append(f"chapter {chapter.number}: running head")
    return found


@pytest.fixture(scope="module")
def ordinary_book(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("furniture") / "ordinary.pdf"
    render_book(path, chapters=chapter_specs(6), running_header=RUNNING_HEAD)
    return path


@pytest.fixture(scope="module")
def margin_heading_book(tmp_path_factory) -> Path:
    """A book whose chapter headings sit where its running head sits.

    Detection strips the furniture first, which takes the headings with it and
    leaves the book reading as chapterless — so it retries over every line.
    That retry is the case where running heads used to stay in the prose.
    """
    chapters = [
        ChapterSpec(number=n, paragraphs=[paragraph(p) for p in spec.paragraphs])
        for n, spec in enumerate(chapter_specs(6), start=1)
    ]
    path = tmp_path_factory.mktemp("furniture") / "margin-headings.pdf"
    # A narrow top margin puts `CHAPTER 1` inside the header band, where its
    # digit-masked signature matches the running head's on every chapter page
    # and it is dropped as furniture. No folios, so the retry is not then
    # refused for finding two heading styles that fit the book equally well.
    render_book(
        path,
        chapters=chapters,
        running_header=RUNNING_HEAD,
        page_numbers=False,
        margin=20.0,
    )
    return path


def test_a_running_head_is_not_part_of_any_chapter(ordinary_book):
    document = ingest_book(ordinary_book, cache=None, use_cache=False).document
    assert furniture_in(document) == []


def test_no_excerpt_in_an_ordinary_book_can_carry_page_furniture(ordinary_book):
    """The end-to-end version: check what would actually be quoted."""
    document = ingest_book(ordinary_book, cache=None, use_cache=False).document
    config = ExcerptConfig()

    for chapter in document.chapters:
        for word in {normalize_term(w) for w in chapter.text.split() if len(w) > 5}:
            for candidate in excerpt_candidates(
                document, word, [chapter.number], config
            ):
                assert RUNNING_HEAD.lower() not in candidate.text.lower()


def test_the_full_text_retry_still_keeps_furniture_out_of_the_prose(
    margin_heading_book,
):
    """The retry needs the running heads to find the headings. Quoting does not.

    Whichever pass produced the chapter map, the paragraphs are assembled from
    prose lines only, so `THE HOLLOW ROAD 143` cannot land in a student excerpt.
    """
    report = ingest_book(
        margin_heading_book, cache=None, use_cache=False, expected_chapters=6
    )

    assert report.chapter_pass == FULL_TEXT_PASS
    assert len(report.document.chapters) == 6
    assert furniture_in(report.document) == []


def test_the_report_says_furniture_went_even_on_the_retry(margin_heading_book):
    """It used to say "none removed" while the furniture sat in the prose.

    The count now describes what happened to the chapter text rather than what
    happened to the detection stream, which are no longer the same thing.
    """
    report = ingest_book(
        margin_heading_book, cache=None, use_cache=False, expected_chapters=6
    )

    if not report.furniture:
        pytest.skip("this rendering produced no repeated running heads")
    assert report.document.stats.furniture_lines_dropped > 0
    assert "none removed" not in report.render()


# --- and no setting can turn that into an export ---------------------------


def test_no_excerpt_policy_lets_an_unconfirmed_passage_reach_ready(
    hyphen_book, tmp_path
):
    """The guarantee is not a default. It is the only behaviour there is.

    `unconfirmed_repairs` decides whether such a passage is *offered* — skipped
    outright, or produced so a person can look at it. Neither value makes it
    exportable, and the check in `verify_item` does not read the config at all.
    """
    from bookengine.vocabulary.models import Status, VocabularyItem

    document = ingest_book(hyphen_book, cache=None, use_cache=False).document
    number, locator = uncertain_locator(document)
    if locator is None:
        pytest.skip("this rendering left no unconfirmed repairs")

    chapter = document.chapter(number)
    for policy in ("skip", "review"):
        job: JobConfig = build_job(
            hyphen_book,
            tmp_path / "out",
            lessons=[{"lesson": 1, "start_chapter": 1, "end_chapter": 4}],
            excerpt={
                "max_characters": 600,
                "min_characters": 10,
                "unconfirmed_repairs": policy,
            },
        )
        item = VocabularyItem(lesson=1, term="corridor", normalized_term="corridor")
        item.locator = locator
        item.excerpt = chapter.slice(locator.char_start, locator.char_end)
        item.definition = "a passage"
        item.korean_meaning = "복도"
        item.excerpt_context = "Mara walks."
        item.status = Status.AUDIT_PENDING

        verification = verify_item(document, job, item)

        assert verification.checks["excerpt_is_confirmed_text"] is False, policy
        assert not verification.ok, policy


def test_a_reviewable_passage_is_parked_rather_than_exported(hyphen_book, tmp_path):
    """`review` produces a row for a person, never a row for a student."""
    from bookengine.export.tsv import exportable_items
    from bookengine.llm.chain import ProviderChain
    from bookengine.prompts import PromptLibrary
    from bookengine.vocabulary.dedupe import DuplicateRegistry
    from bookengine.vocabulary.models import Status
    from bookengine.vocabulary.pipeline import Progress, RunStats, build_lesson
    from fakes import ScriptedProvider

    document = ingest_book(hyphen_book, cache=None, use_cache=False).document
    words = [
        word
        for chapter in document.chapters
        for paragraph in chapter.paragraphs
        if paragraph.uncertain_repair_offsets
        for word in chapter.slice(paragraph.char_start, paragraph.char_end).split()
    ]
    candidates = [
        Candidate(
            term=normalize_term(word),
            sense="s",
            score=RubricScore(4, 4, 4, 4, 4, 1),
        )
        for word in dict.fromkeys(words)
        if len(normalize_term(word)) > 6
    ]
    if not candidates:
        pytest.skip("this rendering left no unconfirmed repairs")

    job = build_job(
        hyphen_book,
        tmp_path / "out",
        vocabulary_per_lesson=8,
        candidates_per_lesson=len(candidates),
        lessons=[{"lesson": 1, "start_chapter": 1, "end_chapter": 4}],
        excerpt={"min_characters": 10, "unconfirmed_repairs": "review"},
    )
    writer = ScriptedProvider()
    produced = build_lesson(
        document,
        job,
        job.lesson(1),
        candidates,
        DuplicateRegistry(job.dedupe),
        ProviderChain(providers=[writer]),
        ProviderChain(providers=[writer.as_auditor()]),
        PromptLibrary(),
        RunStats(),
        Progress(),
    )

    parked = [item for item in produced if item.status is Status.NEEDS_REVIEW]
    if not parked:
        pytest.skip("every candidate here had a confirmed passage available")

    # The passage is on the item, so a person can read it...
    assert all(item.excerpt for item in parked)
    assert all("rejoined across a line break" in item.failures[0] for item in parked)
    # ...and none of them is in what gets pasted into the Sheet.
    exported = {id(item) for item in exportable_items(produced)}
    assert not any(id(item) in exported for item in parked)
