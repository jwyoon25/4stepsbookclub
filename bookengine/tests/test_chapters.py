"""Chapter detection, including the cases where refusing is the right answer."""

from __future__ import annotations

import pytest

from bookengine.errors import ChapterDetectionError
from bookengine.source import layout
from bookengine.source.chapters import (
    detect_chapters,
    parse_number_word,
    parse_roman,
    require_confident_detection,
)
from bookengine.source.pdf import extract_pdf
from fixtures.prose import chapter_specs
from fixtures.synthetic_book import render_book


def detect(tmp_path, **options):
    path = tmp_path / "book.pdf"
    render_book(path, **options)
    book = extract_pdf(path)
    lines = layout.prose_lines(book, layout.detect_furniture(book))
    return detect_chapters(lines)


@pytest.mark.parametrize(
    "style", ["chapter-arabic", "chapter-word", "bare-word", "bare-arabic", "roman"]
)
def test_every_common_heading_style_is_read(tmp_path, style):
    detection = detect(tmp_path, chapters=chapter_specs(12), heading_style=style)
    assert detection.count == 12
    assert detection.confidence == "high"
    assert detection.numbers == list(range(1, 13))


def test_a_contents_page_is_not_mistaken_for_the_chapters(tmp_path):
    """The classic false positive: twelve headings listed on page four."""
    contents = ["CONTENTS", *[f"Chapter {n} .......... {n * 11}" for n in range(1, 13)]]
    detection = detect(
        tmp_path, chapters=chapter_specs(12), front_matter=contents
    )
    assert detection.count == 12
    assert detection.confidence == "high"
    # Chapter 1 starts after the contents page, not on it.
    assert detection.headings[0].page > 1


def test_chapter_titles_are_kept_apart_from_chapter_numbers(tmp_path):
    titles = {1: "The Box", 2: "The Glade", 3: "The Wall"}
    detection = detect(
        tmp_path, chapters=chapter_specs(3, titles), heading_style="chapter-arabic"
    )
    assert [heading.title for heading in detection.headings] == [
        "The Box",
        "The Glade",
        "The Wall",
    ]


def test_back_matter_is_located_so_it_can_be_excluded(tmp_path):
    detection = detect(
        tmp_path,
        chapters=chapter_specs(6),
        back_matter=["ACKNOWLEDGMENTS", "Thanks to everyone who read early drafts."],
    )
    assert detection.back_matter_line is not None


def test_an_unusual_book_needs_a_human_to_confirm_the_count(tmp_path):
    """Chapters that run on without a page break are legal but suspicious."""
    detection = detect(
        tmp_path,
        chapters=chapter_specs(6),
        chapter_starts_new_page=False,
        running_header=None,
        page_numbers=False,
    )
    assert detection.confidence == "acceptable"
    assert detection.warnings

    with pytest.raises(ChapterDetectionError):
        require_confident_detection(detection, book_name="book.pdf")

    # The operator's own count clears a warning...
    require_confident_detection(detection, book_name="book.pdf", expected_chapters=6)

    # ...but only when it agrees.
    with pytest.raises(ChapterDetectionError):
        require_confident_detection(
            detection, book_name="book.pdf", expected_chapters=7
        )


def test_a_disagreeing_chapter_count_stops_the_run(tmp_path):
    detection = detect(tmp_path, chapters=chapter_specs(12))
    with pytest.raises(ChapterDetectionError) as failure:
        require_confident_detection(
            detection, book_name="the-maze-runner.pdf", expected_chapters=62
        )
    message = str(failure.value)
    assert "expects 62 chapters and detection found 12" in message
    assert "aborted" in message


@pytest.mark.parametrize(
    ("word", "expected"),
    [("ONE", 1), ("Seven", 7), ("TWENTY-THREE", 23), ("Thirty One", 31), ("BOX", None)],
)
def test_number_words_are_read_and_other_words_are_not(word, expected):
    assert parse_number_word(word) == expected


@pytest.mark.parametrize(
    ("numeral", "expected"),
    [("I", 1), ("IV", 4), ("XIV", 14), ("IIII", None), ("MIX", None), ("", None)],
)
def test_only_canonical_roman_numerals_are_read(numeral, expected):
    assert parse_roman(numeral) == expected


# --- the epilogue ----------------------------------------------------------

# A word that appears only after the EPILOGUE line, so its presence in the last
# chapter is proof the boundary did not hold.
MEMO_MARKER = "chancelor"

EPILOGUE_MEMO = [
    "EPILOGUE",
    f"Internal memorandum from Ava Paige, {MEMO_MARKER}. The trial results "
    "were most extraordinary, and the subjects will be allowed one full "
    "night of sleep before the next stage begins.",
]


def epilogue_book(tmp_path, count: int = 6):
    """A novel whose last chapter is followed by an unnumbered epilogue."""
    from bookengine.source.ingest import ingest_book

    chapters = chapter_specs(count)
    path = tmp_path / "with-epilogue.pdf"
    render_book(path, chapters=chapters, back_matter=EPILOGUE_MEMO)
    return ingest_book(path, cache=None, use_cache=False).document, chapters


def test_an_epilogue_ends_the_last_chapter(tmp_path):
    """It is still the story, and that is exactly why it has to be cut off.

    An epilogue is not a numbered chapter, so no chapter reference is true of
    it. Left attached, its sentences are quotable, they verify, and they are
    cited as the last chapter to a student who will not find them there — which
    is what The Maze Runner did before this.
    """
    document, chapters = epilogue_book(tmp_path)
    last = document.chapter(len(chapters))

    assert "EPILOGUE" not in last.text.upper()
    assert MEMO_MARKER not in last.text.lower()


def test_the_epilogue_does_not_cost_the_book_a_chapter(tmp_path):
    """The boundary trims the last chapter; it must not drop or renumber one."""
    document, chapters = epilogue_book(tmp_path)

    assert document.chapter_numbers == [c.number for c in chapters]


def test_the_last_chapter_still_ends_on_its_own_last_sentence(tmp_path):
    document, chapters = epilogue_book(tmp_path)
    written = chapters[-1].paragraphs[-1]

    assert document.chapter(len(chapters)).text.endswith(written[-40:])


def test_epilogue_prose_cannot_be_quoted_or_cited(tmp_path):
    """The end-to-end version: no locator in the book reaches that text."""
    from bookengine.source.search import find_occurrences

    document, _ = epilogue_book(tmp_path)

    assert find_occurrences(document, MEMO_MARKER) == []
    assert find_occurrences(document, "memorandum") == []


def test_a_book_without_an_epilogue_is_unaffected(tmp_path):
    """The control: the marker only bites when the book actually has one."""
    from bookengine.source.ingest import ingest_book

    chapters = chapter_specs(6)
    path = tmp_path / "no-epilogue.pdf"
    render_book(path, chapters=chapters)
    document = ingest_book(path, cache=None, use_cache=False).document
    written = chapters[-1].paragraphs[-1]

    assert document.chapter_numbers == [c.number for c in chapters]
    assert document.chapter(6).text.endswith(written[-40:])
