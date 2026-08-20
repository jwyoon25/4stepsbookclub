"""Running the ingestion stages in order, and refusing when they disagree.

Each stage below this one answers a narrow question and none of them decides
whether the book as a whole is usable. This module does. It is the layer that
is allowed to say no: an image-only scan, and a chapter map that two heading
styles explain equally well, both stop the run here — before a model is called,
and long before a workbook page carries a chapter number nobody checked.

It also owns the one piece of recovery in ingestion. Page furniture is stripped
before chapter detection, because a running head repeated three hundred times
otherwise looks like the most dependable heading in the book. But some books
set their chapter headings in the same margin band as the running head, and for
those the strip takes the headings with it and the book reads as chapterless.
So a first pass that finds nothing is retried once against the untouched line
stream. The report names the pass that produced the chapter map, because a map
built the second way comes with the running heads still sitting in the prose,
which is worth knowing before quoting from it.

The report itself is written for a person. Ingestion cannot tell a misdetected
chapter from a genuinely short one and should not pretend to; what it can do is
put the numbers where an operator will see them, and say plainly which ones
look wrong.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import UnsupportedBookError
from .cache import ParseCache
from .chapters import (
    MIN_CHAPTER_CHARACTERS,
    ChapterDetection,
    ChapterHeading,
    detect_chapters,
    require_confident_detection,
)
from .document import BookDocument, Chapter, build_document
from .layout import (
    FurnitureRecord,
    detect_furniture,
    page_metrics,
    prose_lines,
)
from .pdf import (
    MAX_SPARSE_PAGE_SHARE,
    ExtractedBook,
    content_hash,
    extract_pdf,
)

# What the two chapter-detection passes are called in the report.
STRIPPED_PASS = "page furniture removed"
FULL_TEXT_PASS = "full text, after the first pass found no chapters"

# Above this many chapters the listing is elided in the middle rather than
# running for two screens. The count omitted is always stated.
MAX_CHAPTERS_LISTED = 30
EDGE_CHAPTERS_LISTED = 5

# A chapter this much shorter than the book's typical chapter is more often a
# heading matched inside the prose than a genuinely short chapter.
SHORT_CHAPTER_SHARE = 0.25

# Rejoining a word broken across a line is the one ingestion step that changes
# the characters that later get quoted, and it cannot distinguish a hyphen the
# typesetter inserted from one the author wrote. At roughly one repair per two
# paragraphs, the book hyphenates often enough that some real hyphens have
# almost certainly been removed, so an operator should read a few excerpts.
HIGH_REPAIR_PER_PARAGRAPH = 0.5

# Well under the share at which `extract_pdf` refuses the book outright, but
# enough near-empty pages to be worth a look: it is what a part-title-heavy
# book and a partly scanned one both look like from here.
NOTABLE_SPARSE_PAGE_SHARE = 0.10

_LABEL_WIDTH = 32


@dataclass(slots=True)
class IngestionReport:
    """Everything one ingestion produced, including what to look at by hand.

    `notes` are advisory by definition. Anything that makes the book unusable
    has already been raised by the time this exists, so a note is always
    something a person can judge and the engine cannot.
    """

    document: BookDocument
    from_cache: bool
    furniture: list[FurnitureRecord] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Which detection pass produced the chapter map. A cached document does not
    # record it, so on that path it is unknown rather than assumed.
    chapter_pass: str | None = None

    @property
    def chapter_count(self) -> int:
        return len(self.document.chapters)

    def render(self) -> str:
        """The report an operator reads before trusting a chapter map."""
        document = self.document
        stats = document.stats

        rows = [
            _row("Book", document.source_name),
            _row("Title", document.title),
            _row("Pages", f"{document.page_count:,}"),
            _row("Source", "parse cache" if self.from_cache else "parsed this run"),
            _row("Detected chapters", _detection_summary(document)),
        ]
        if self.chapter_pass is not None:
            rows.append(_row("Chapter detection pass", self.chapter_pass))

        rows.append("")
        rows.extend(_chapter_rows(document.chapters))
        rows.append("")

        rows.extend(
            [
                self._furniture_row(),
                _row("Words rejoined across lines", f"{stats.hyphen_repairs:,}"),
                _row(
                    "Paragraphs / sentences",
                    f"{stats.paragraphs:,} / {stats.sentences:,}",
                ),
                _row("Characters of prose", f"{stats.characters:,}"),
                _row(
                    "Front / back matter lines",
                    f"{stats.front_matter_lines:,} / {stats.back_matter_lines:,}",
                ),
            ]
        )

        if self.notes:
            rows.append("")
            rows.append("Notes")
            rows.extend(f"  - {note}" for note in self.notes)

        return "\n".join(rows)

    def _furniture_row(self) -> str:
        """The running-head line, which has to cover the case where none went.

        On the full-text retry the furniture was found and deliberately kept,
        and reporting that as "0 lines" would read as "none found" — the
        opposite of what happened.
        """
        dropped = self.document.stats.furniture_lines_dropped
        examples = _examples(record.signature for record in self.furniture)

        if dropped:
            detail = f"{dropped:,} lines" + (f" ({examples})" if examples else "")
        elif self.furniture:
            detail = f"none removed; {len(self.furniture)} kept for the retry"
            detail += f" ({examples})" if examples else ""
        else:
            detail = "none found"

        return _row("Running heads removed", detail)


def ingest_book(
    path: Path | str,
    *,
    title: str | None = None,
    expected_chapters: int | None = None,
    cache: ParseCache | None = None,
    use_cache: bool = True,
) -> IngestionReport:
    """Turn a PDF into a document the rest of the engine can quote from.

    `expected_chapters` is the operator's own count, read off the book's
    contents page, and it is checked on the cached path exactly as it is on the
    fresh one. A cache is a way to skip work, never a way to skip a refusal.
    """
    path = Path(path)
    if not path.is_file():
        raise UnsupportedBookError(f"No such book file: {path}")

    book_title = title or _title_from(path)
    caching = cache is not None and use_cache

    if caching:
        # Hashing the file is cheap next to parsing it, so the key is computed
        # before anything is opened as a PDF.
        cached = cache.load(content_hash(path))
        if cached is not None:
            return _from_cache(
                cached,
                book_name=path.name,
                title=title,
                expected_chapters=expected_chapters,
            )

    book = extract_pdf(path)
    furniture = detect_furniture(book)

    stripped = prose_lines(book, furniture)
    detection = detect_chapters(stripped)
    lines = stripped
    chapter_pass = STRIPPED_PASS
    dropped = furniture.dropped_count
    notes: list[str] = []

    if not detection.headings:
        # A book whose headings live in the margin band loses them to the
        # furniture strip. Detection has to run on the same line list the
        # document is built from — the headings carry indices into it — so the
        # retry keeps the furniture in the prose as well as in the search.
        whole = prose_lines(book, None)
        retried = detect_chapters(whole)
        if retried.headings:
            detection = retried
            lines = whole
            chapter_pass = FULL_TEXT_PASS
            dropped = 0
            notes.append(
                "Chapter headings were only found once page furniture was put "
                "back, so this book's headings sit in the margin band. Running "
                "heads and page numbers remain inside the chapter text and will "
                "appear in quotations drawn from a page break."
            )

    metrics = page_metrics(lines)
    require_confident_detection(
        detection, book_name=path.name, expected_chapters=expected_chapters
    )

    document = build_document(
        book,
        detection,
        lines,
        metrics,
        title=book_title,
        furniture_dropped=dropped,
    )

    notes.extend(_detection_notes(document))
    notes.extend(_chapter_size_notes(document))
    notes.extend(_repair_notes(document))
    notes.extend(_sparse_page_notes(book))

    if cache is not None and use_cache:
        cache.store(document)
    elif cache is not None:
        notes.append(
            "The parse cache was bypassed for this run, so nothing was read "
            "from it and nothing was written to it."
        )

    return IngestionReport(
        document=document,
        from_cache=False,
        furniture=list(furniture.records),
        notes=notes,
        chapter_pass=chapter_pass,
    )


def _from_cache(
    document: BookDocument,
    *,
    book_name: str,
    title: str | None,
    expected_chapters: int | None,
) -> IngestionReport:
    """Build the report for a cache hit, applying the same refusals.

    The title is the operator's label rather than something parsing derived, so
    a renamed book is updated in place instead of forcing a reparse.
    """
    if title is not None and document.title != title:
        document.title = title

    require_confident_detection(
        _restored_detection(document),
        book_name=book_name,
        expected_chapters=expected_chapters,
    )

    notes = [
        "This document came from the parse cache. Clear the cache to reparse "
        "the PDF from scratch."
    ]
    notes.extend(_detection_notes(document))
    notes.extend(_chapter_size_notes(document))
    notes.extend(_repair_notes(document))

    return IngestionReport(document=document, from_cache=True, notes=notes)


def _restored_detection(document: BookDocument) -> ChapterDetection:
    """The detection result as far as a cached document still remembers it.

    Only the chapter count, the style, the confidence and the warnings survive
    being written to the cache — and those are exactly the fields
    `require_confident_detection` reads, which is why the check can be the same
    one. The line positions are filled from each chapter so the object is well
    formed; nothing on this path consults them.
    """
    issues: list[str] = []
    if document.detection_confidence == "low":
        issues.append("The cached parse recorded low-confidence chapter detection.")

    headings = [
        ChapterHeading(
            number=chapter.number,
            title=chapter.title,
            raw=chapter.heading,
            line_index=index,
            page=chapter.page_start,
            starts_page=True,
        )
        for index, chapter in enumerate(document.chapters)
    ]

    return ChapterDetection(
        style=document.detection_style,
        headings=headings,
        confidence=document.detection_confidence,
        issues=issues,
        warnings=list(document.detection_warnings),
        considered={document.detection_style or "unknown": len(headings)},
    )


def _detection_notes(document: BookDocument) -> list[str]:
    """Say out loud that a chapter map was accepted with reservations."""
    notes: list[str] = []

    if document.detection_confidence != "high":
        notes.append(
            f"Chapter detection reported {document.detection_confidence} "
            f"confidence using the {document.detection_style or 'unknown'} "
            "style. Check the first and last chapters in the listing against "
            "the book itself."
        )

    notes.extend(document.detection_warnings)
    return notes


def _chapter_size_notes(document: BookDocument) -> list[str]:
    """Point at chapters whose length does not look like a chapter's.

    A heading matched inside the prose produces a chapter of a few hundred
    characters sitting between two ordinary ones, and nothing downstream would
    notice: the quotations would all be real and all be filed under the wrong
    number.
    """
    chapters = document.chapters
    if not chapters:
        return []

    notes: list[str] = []
    sizes = [len(chapter.text) for chapter in chapters]

    tiny = [
        chapter.number
        for chapter in chapters
        if len(chapter.text) < MIN_CHAPTER_CHARACTERS
    ]
    if tiny:
        notes.append(
            f"{_numbered(tiny)} under {MIN_CHAPTER_CHARACTERS} characters of "
            "prose, which is usually a heading matched inside the text rather "
            "than a chapter."
        )

    if len(chapters) >= 3:
        typical = statistics.median(sizes)
        threshold = typical * SHORT_CHAPTER_SHARE
        already_flagged = set(tiny)
        short = [
            chapter.number
            for chapter in chapters
            if len(chapter.text) < threshold and chapter.number not in already_flagged
        ]
        if short:
            notes.append(
                f"{_numbered(short)} under {SHORT_CHAPTER_SHARE:.0%} the length "
                f"of a typical chapter in this book ({typical:,.0f} characters). "
                "Check the chapter map around them."
            )

    return notes


def _repair_notes(document: BookDocument) -> list[str]:
    stats = document.stats
    if not stats.paragraphs:
        return []

    rate = stats.hyphen_repairs / stats.paragraphs
    if rate < HIGH_REPAIR_PER_PARAGRAPH:
        return []

    return [
        f"{stats.hyphen_repairs:,} words were rejoined across a line break, "
        f"about {rate:.2f} per paragraph. At that rate this book hyphenates "
        "heavily enough that a hyphen the author wrote has probably been "
        "removed somewhere; excerpt selection prefers passages with no repairs "
        "in them, but read a few of the quotations."
    ]


def _sparse_page_notes(book: ExtractedBook) -> list[str]:
    """Flag near-empty pages, which are illustrations or a partial scan."""
    if not book.page_count:
        return []

    share = len(book.sparse_pages) / book.page_count
    if share < NOTABLE_SPARSE_PAGE_SHARE:
        return []

    listed = _examples((str(page) for page in book.sparse_pages), quote=False)
    return [
        f"{len(book.sparse_pages)} of {book.page_count} pages ({share:.0%}) "
        f"carry almost no text: {listed}. Illustrations and part titles look "
        f"like this, and so does a partly scanned book; the run is refused "
        f"above {MAX_SPARSE_PAGE_SHARE:.0%}."
    ]


def _detection_summary(document: BookDocument) -> str:
    return (
        f"{len(document.chapters)}  (style: "
        f"{document.detection_style or 'unrecognised'}, "
        f"confidence: {document.detection_confidence})"
    )


def _chapter_rows(chapters: list[Chapter]) -> list[str]:
    """One line per chapter, elided in the middle for a long book.

    The elision states its own size. A listing that quietly stopped at twenty
    would hide exactly the chapters worth checking, since a misdetection lands
    at the end as often as at the start.
    """
    if not chapters:
        return ["No chapters."]

    if len(chapters) <= MAX_CHAPTERS_LISTED:
        return [_chapter_row(chapter) for chapter in chapters]

    head = chapters[:EDGE_CHAPTERS_LISTED]
    tail = chapters[-EDGE_CHAPTERS_LISTED:]
    omitted = len(chapters) - len(head) - len(tail)
    return [
        *(_chapter_row(chapter) for chapter in head),
        f"... {omitted} chapters not listed ...",
        *(_chapter_row(chapter) for chapter in tail),
    ]


def _chapter_row(chapter: Chapter) -> str:
    pages = (
        f"pages {chapter.page_start}-{chapter.page_end}"
        if chapter.page_end > chapter.page_start
        else f"page {chapter.page_start}"
    )
    label = f"Chapter {chapter.number}"
    return f"{label:<12}{pages:<16}{len(chapter.text):>9,} characters"


def _row(label: str, value: str) -> str:
    return f"{label.ljust(_LABEL_WIDTH, '.')} {value}"


def _examples(values: Iterable[str], *, limit: int = 3, quote: bool = True) -> str:
    """A short sample of a list, always saying how much it left out."""
    items = list(values)
    shown = ", ".join(f'"{item}"' if quote else str(item) for item in items[:limit])
    if len(items) <= limit:
        return shown
    return f"{shown}, and {len(items) - limit} more"


def _numbered(numbers: list[int], limit: int = 8) -> str:
    """`Chapter 4 is` / `Chapters 4, 9 and 2 more are`, as a sentence opener."""
    shown = ", ".join(str(number) for number in numbers[:limit])
    if len(numbers) > limit:
        shown = f"{shown} and {len(numbers) - limit} more"
    if len(numbers) == 1:
        return f"Chapter {shown} is"
    return f"Chapters {shown} are"


def _title_from(path: Path) -> str:
    """The same title `load_job` derives, so both routes name a book alike."""
    return path.stem.replace("-", " ").replace("_", " ").strip()
