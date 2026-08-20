"""A small novel, laid out into a real PDF, with its answers known.

Testing ingestion against a real book would mean committing a copyrighted one,
and testing it against a hand-written string would skip the part that actually
breaks: extraction. So the fixtures build genuine PDFs — running heads, page
numbers, first-line indents, words hyphenated across a line break, curly
quotes — and hand back the ground truth alongside, so a test can assert that
what came out is what went in.

The body face is the repository's own vendored Gowun Batang. PDF base-14 Times
cannot encode a typographic quotation mark, and a fixture book that only ever
contains ASCII apostrophes would never exercise the character folding that real
books make necessary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FONT_DIRECTORY = REPOSITORY_ROOT / "workbooks" / "assets" / "fonts"
BODY_FONT_FILE = FONT_DIRECTORY / "GowunBatang-Regular.ttf"
HEADING_FONT_FILE = FONT_DIRECTORY / "GowunBatang-Bold.ttf"

BODY_FONT_NAME = "fixturebody"
HEADING_FONT_NAME = "fixturehead"

_BODY = pymupdf.Font(fontfile=str(BODY_FONT_FILE))
_HEADING = pymupdf.Font(fontfile=str(HEADING_FONT_FILE))


@dataclass
class ChapterSpec:
    """One chapter as the fixture author wrote it."""

    number: int
    title: str | None = None
    paragraphs: list[str] = field(default_factory=list)


@dataclass
class BookTruth:
    """What the rendered PDF is known to contain."""

    path: Path
    chapters: list[ChapterSpec]
    pages_per_chapter: dict[int, list[int]]
    page_count: int

    def paragraph_texts(self, number: int) -> list[str]:
        for chapter in self.chapters:
            if chapter.number == number:
                return list(chapter.paragraphs)
        raise KeyError(number)

    @property
    def numbers(self) -> list[int]:
        return [chapter.number for chapter in self.chapters]


NUMBER_WORDS = [
    "ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT",
    "NINE", "TEN", "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN",
    "SIXTEEN", "SEVENTEEN", "EIGHTEEN", "NINETEEN", "TWENTY", "TWENTY-ONE",
    "TWENTY-TWO", "TWENTY-THREE", "TWENTY-FOUR",
]

ROMAN = [
    "", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI",
    "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI",
    "XXII", "XXIII", "XXIV",
]


def heading_for(style: str, chapter: ChapterSpec) -> str:
    """Render a chapter heading in one of the styles real books use."""
    number = chapter.number
    if style == "chapter-arabic":
        text = f"CHAPTER {number}"
    elif style == "chapter-word":
        text = f"Chapter {NUMBER_WORDS[number].title()}"
    elif style == "bare-word":
        text = NUMBER_WORDS[number]
    elif style == "bare-arabic":
        text = str(number)
    elif style == "roman":
        text = f"CHAPTER {ROMAN[number]}"
    else:
        raise ValueError(f"Unknown heading style: {style}")

    if chapter.title and style in {"chapter-arabic", "chapter-word"}:
        text = f"{text}: {chapter.title}"
    return text


def _wrap(
    text: str,
    *,
    size: float,
    available: float,
    indent: float,
    hyphenate: bool,
) -> list[tuple[float, str]]:
    """Break one paragraph into laid-out lines of (x offset, text).

    Deliberately includes forced hyphenation, because a justified book does it
    on nearly every page, and an ingester that cannot rejoin `incompre-` and
    `hensible` will never find half the vocabulary in the book.
    """
    lines: list[tuple[float, str]] = []
    current: list[str] = []
    offset = indent

    def flush() -> None:
        nonlocal current, offset
        if current:
            lines.append((offset, " ".join(current)))
            current = []
            offset = 0.0

    def fits(words: list[str]) -> bool:
        return _BODY.text_length(" ".join(words), size) <= available - offset

    for word in text.split():
        if fits([*current, word]):
            current.append(word)
            continue

        if hyphenate and len(word) >= 10 and current:
            for split in range(len(word) // 2 + 2, 3, -1):
                if fits([*current, word[:split] + "-"]):
                    current.append(word[:split] + "-")
                    flush()
                    current = [word[split:]]
                    break
            else:
                flush()
                current = [word]
            continue

        flush()
        current = [word]

    flush()
    return lines


def render_book(
    path: Path | str,
    *,
    chapters: list[ChapterSpec],
    heading_style: str = "chapter-arabic",
    running_header: str | None = "THE HOLLOW ROAD",
    page_numbers: bool = True,
    front_matter: list[str] | None = None,
    back_matter: list[str] | None = None,
    page_size: tuple[float, float] = (396, 612),
    margin: float = 54.0,
    size: float = 10.5,
    leading: float = 14.0,
    indent: float = 16.0,
    hyphenate: bool = True,
    chapter_starts_new_page: bool = True,
) -> BookTruth:
    """Lay the chapters out into a PDF and report where everything landed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open()
    width, height = page_size
    available = width - 2 * margin
    top = margin + 24.0
    bottom = height - margin - 18.0

    page: pymupdf.Page | None = None
    y = top
    page_number = 0
    dirty = False
    pages_per_chapter: dict[int, list[int]] = {}
    current_chapter: int | None = None

    def start_page() -> None:
        nonlocal page, y, page_number, dirty
        page = document.new_page(width=width, height=height)
        page_number += 1
        y = top
        dirty = False

        if running_header:
            page.insert_text(
                (margin, margin),
                running_header,
                fontname=HEADING_FONT_NAME,
                fontfile=str(HEADING_FONT_FILE),
                fontsize=8,
            )
        if page_numbers:
            label = str(page_number)
            page.insert_text(
                (width / 2 - _BODY.text_length(label, 8) / 2, height - margin + 8),
                label,
                fontname=BODY_FONT_NAME,
                fontfile=str(BODY_FONT_FILE),
                fontsize=8,
            )
        if current_chapter is not None:
            pages_per_chapter.setdefault(current_chapter, [])
            if page_number not in pages_per_chapter[current_chapter]:
                pages_per_chapter[current_chapter].append(page_number)

    def ensure_room() -> None:
        if page is None or y > bottom:
            start_page()

    def put(text: str, *, x: float, bold: bool, font_size: float) -> None:
        nonlocal dirty
        page.insert_text(
            (x, y),
            text,
            fontname=HEADING_FONT_NAME if bold else BODY_FONT_NAME,
            fontfile=str(HEADING_FONT_FILE if bold else BODY_FONT_FILE),
            fontsize=font_size,
        )
        dirty = True

    def write_paragraph(text: str, *, first_indent: float) -> None:
        nonlocal y
        for offset, line in _wrap(
            text,
            size=size,
            available=available,
            indent=first_indent,
            hyphenate=hyphenate,
        ):
            ensure_room()
            put(line, x=margin + offset, bold=False, font_size=size)
            y += leading

    for block in front_matter or []:
        ensure_room()
        write_paragraph(block, first_indent=0.0)
        y += leading

    for chapter in chapters:
        current_chapter = chapter.number
        if page is None or (chapter_starts_new_page and dirty):
            start_page()
        elif dirty:
            y += leading * 2
        pages_per_chapter.setdefault(chapter.number, [])
        if page_number not in pages_per_chapter[chapter.number]:
            pages_per_chapter[chapter.number].append(page_number)

        heading = heading_for(heading_style, chapter)
        ensure_room()
        put(
            heading,
            x=margin + (available - _HEADING.text_length(heading, size + 3)) / 2,
            bold=True,
            font_size=size + 3,
        )
        y += leading * 2.5

        for index, paragraph in enumerate(chapter.paragraphs):
            write_paragraph(paragraph, first_indent=0.0 if index == 0 else indent)

    current_chapter = None
    for block in back_matter or []:
        start_page()
        write_paragraph(block, first_indent=0.0)

    document.save(path)
    page_count = document.page_count
    document.close()

    return BookTruth(
        path=path,
        chapters=chapters,
        pages_per_chapter=pages_per_chapter,
        page_count=page_count,
    )
