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
