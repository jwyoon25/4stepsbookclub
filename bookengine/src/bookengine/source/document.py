"""The book as a structure that can be quoted from and cited.

Everything above this module treats a `BookDocument` as the truth about a book:
which chapters exist, what text is in them, and where any given sentence sits.
That is the whole reason it exists. A quotation in a workbook is not a string
that an LLM produced and something later checked — it is a slice of
`Chapter.text` taken at recorded offsets, and the check is that re-taking the
slice gives the same characters back.

Two invariants hold and are tested:

    chapter.text[paragraph.char_start:paragraph.char_end] == paragraph text
    chapter.text[sentence.char_start:sentence.char_end]   == sentence text

Nothing in this module is specific to vocabulary. A comprehension-question
generator or a lesson summariser would want exactly this and nothing more.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pysbd

from .chapters import ChapterDetection
from .layout import PageMetrics, assemble_paragraphs
from .pdf import ExtractedBook, TextLine
from .text import normalize_with_offsets

_SEGMENTER = pysbd.Segmenter(language="en", clean=False, char_span=True)

# Paragraphs are joined by a blank line, so an excerpt that contains one has
# crossed a paragraph boundary and is not a quotation from a single passage.
PARAGRAPH_SEPARATOR = "\n\n"


@dataclass(frozen=True, slots=True)
class Paragraph:
    """One paragraph, located in its chapter's text.

    Two lists of repair offsets, not one. `repair_offsets` is every word this
    engine rejoined across a line break, which is what the ingestion report
    counts. `uncertain_repair_offsets` is the subset the book itself could not
    settle — where `self-conscious` and `selfconscious` were equally consistent
    with the rest of the novel — and those are the only ones that stop a
    passage being quoted, because those are the only ones that might be wrong.
    """

    id: str
    chapter: int
    page_start: int
    page_end: int
    char_start: int
    char_end: int
    repair_offsets: tuple[int, ...] = ()
    uncertain_repair_offsets: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class Sentence:
    """One sentence, located in its chapter's text."""

    id: str
    chapter: int
    paragraph_id: str
    page: int
    char_start: int
    char_end: int


@dataclass(slots=True)
class Chapter:
    """One chapter's canonical text, and the map of what is where inside it."""

    number: int
    title: str | None
    heading: str
    page_start: int
    page_end: int
    text: str
    paragraphs: list[Paragraph] = field(default_factory=list)
    sentences: list[Sentence] = field(default_factory=list)
    _comparison: tuple[str, list[int], list[int]] | None = field(
        default=None, repr=False, compare=False
    )

    def _compare(self) -> tuple[str, list[int], list[int]]:
        """The chapter in comparison form, with its offset map, built once.

        Every occurrence search in the book runs against this, so rebuilding it
        per query would make searching quadratic in the size of the book.
        """
        if self._comparison is None:
            self._comparison = normalize_with_offsets(self.text)
        return self._comparison

    @property
    def normalized(self) -> str:
        return self._compare()[0]

    def raw_span(self, normalized_start: int, normalized_end: int) -> tuple[int, int]:
        """Map a span found in comparison form back onto the chapter's own text.

        This is the hinge of the whole design. Searching happens in a form that
        ignores how the PDF spelled a dash; quoting happens in the book's own
        characters. Without this mapping one of those two has to give, and
        neither is allowed to.
        """
        _, starts, ends = self._compare()
        if not 0 <= normalized_start < normalized_end <= len(starts):
            raise IndexError(
                f"Span [{normalized_start}, {normalized_end}) is outside "
                f"chapter {self.number}."
            )
        return starts[normalized_start], ends[normalized_end - 1]

    @property
    def pages(self) -> list[int]:
        return list(range(self.page_start, self.page_end + 1))

    def slice(self, char_start: int, char_end: int) -> str:
        return self.text[char_start:char_end]

    def paragraph(self, paragraph_id: str) -> Paragraph:
        for paragraph in self.paragraphs:
            if paragraph.id == paragraph_id:
                return paragraph
        raise KeyError(paragraph_id)

    def sentence(self, sentence_id: str) -> Sentence:
        for sentence in self.sentences:
            if sentence.id == sentence_id:
                return sentence
        raise KeyError(sentence_id)

    def paragraph_containing(self, offset: int) -> Paragraph | None:
        for paragraph in self.paragraphs:
            if paragraph.char_start <= offset < paragraph.char_end:
                return paragraph
        return None

    def sentence_containing(self, offset: int) -> Sentence | None:
        for sentence in self.sentences:
            if sentence.char_start <= offset < sentence.char_end:
                return sentence
        return None


@dataclass(slots=True)
class IngestionStats:
    """What ingestion did, in numbers an operator can sanity-check."""

    pages: int = 0
    lines_extracted: int = 0
    furniture_lines_dropped: int = 0
    front_matter_lines: int = 0
    back_matter_lines: int = 0
    paragraphs: int = 0
    sentences: int = 0
    characters: int = 0
    hyphen_repairs: int = 0
    hyphen_repairs_uncertain: int = 0


@dataclass(slots=True)
class BookDocument:
    """A whole book, ingested."""

    title: str
    source_name: str
    content_hash: str
    page_count: int
    chapters: list[Chapter]
    detection_style: str | None
    detection_confidence: str
    detection_warnings: list[str] = field(default_factory=list)
    stats: IngestionStats = field(default_factory=IngestionStats)

    @property
    def chapter_numbers(self) -> list[int]:
        return [chapter.number for chapter in self.chapters]

    def chapter(self, number: int) -> Chapter:
        for chapter in self.chapters:
            if chapter.number == number:
                return chapter
        raise KeyError(f"The book has no chapter {number}.")

    def has_chapter(self, number: int) -> bool:
        return any(chapter.number == number for chapter in self.chapters)

    def chapters_in_range(self, start: int, end: int) -> list[Chapter]:
        return [
            chapter for chapter in self.chapters if start <= chapter.number <= end
        ]

    def sentence(self, sentence_id: str) -> tuple[Chapter, Sentence]:
        for chapter in self.chapters:
            for sentence in chapter.sentences:
                if sentence.id == sentence_id:
                    return chapter, sentence
        raise KeyError(sentence_id)


def _segment_sentences(text: str) -> list[tuple[int, int]]:
    """Sentence spans within one paragraph, as (start, end) offsets.

    pysbd returns spans that keep the trailing space between sentences, which
    would make a quotation carry a space it does not need. They are trimmed
    back to the characters that are actually the sentence.
    """
    spans: list[tuple[int, int]] = []
    for span in _SEGMENTER.segment(text):
        start, end = span.start, span.end
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end > start:
            spans.append((start, end))
    return spans


def build_document(
    book: ExtractedBook,
    detection: ChapterDetection,
    lines: list[TextLine],
    metrics: PageMetrics,
    *,
    title: str,
    furniture_dropped: int = 0,
    lexicon: frozenset[str] | None = None,
) -> BookDocument:
    """Assemble chapters, paragraphs, and sentences into the book's structure.

    Chapter bodies run from just after their heading line to just before the
    next one. Front matter and back matter are simply not in the document: a
    lesson cannot reference them, and a quotation drawn from an acknowledgements
    page would be worse than no quotation at all. Lines marked as page furniture
    are not in it either, whichever detection pass produced the headings.

    `lexicon` is the book's own unbroken vocabulary, used to decide what a word
    split across a line ending was. It is passed in rather than derived here
    because it has to be built from the whole book: a chapter is far too small
    a sample to say whether this novel writes `self-conscious` or not.
    """
    stats = IngestionStats(
        pages=book.page_count,
        lines_extracted=len(lines),
        furniture_lines_dropped=furniture_dropped,
        front_matter_lines=(
            detection.headings[0].line_index if detection.headings else 0
        ),
    )

    body_end = detection.back_matter_line or len(lines)
    stats.back_matter_lines = len(lines) - body_end

    chapters: list[Chapter] = []

    for position, heading in enumerate(detection.headings):
        start = heading.line_index + 1
        if position + 1 < len(detection.headings):
            end = detection.headings[position + 1].line_index
        else:
            end = body_end
        end = max(start, min(end, body_end))

        # Detection needed every line, including the running heads a book may
        # set its headings beside. A quotation needs none of them: this is the
        # point where the two streams part, and only prose goes on.
        chapter_lines = [line for line in lines[start:end] if not line.furniture]
        assembled = assemble_paragraphs(chapter_lines, metrics, lexicon)

        pieces: list[str] = []
        paragraphs: list[Paragraph] = []
        sentences: list[Sentence] = []
        offset = 0

        for index, block in enumerate(assembled):
            if not block.text:
                continue
            paragraph_id = f"ch{heading.number}-p{block.page_start}-para{index:03d}"
            paragraph = Paragraph(
                id=paragraph_id,
                chapter=heading.number,
                page_start=block.page_start,
                page_end=block.page_end,
                char_start=offset,
                char_end=offset + len(block.text),
                repair_offsets=tuple(block.repair_offsets),
                uncertain_repair_offsets=tuple(block.uncertain_repair_offsets),
            )
            paragraphs.append(paragraph)

            for span_start, span_end in _segment_sentences(block.text):
                sentences.append(
                    Sentence(
                        id=(
                            f"ch{heading.number}-p{block.page_start}"
                            f"-s{len(sentences):03d}"
                        ),
                        chapter=heading.number,
                        paragraph_id=paragraph_id,
                        page=block.page_start,
                        char_start=offset + span_start,
                        char_end=offset + span_end,
                    )
                )

            pieces.append(block.text)
            offset += len(block.text) + len(PARAGRAPH_SEPARATOR)

        text = PARAGRAPH_SEPARATOR.join(pieces)
        pages = [line.page for line in chapter_lines] or [heading.page]

        chapters.append(
            Chapter(
                number=heading.number,
                title=heading.title,
                heading=heading.raw,
                page_start=min(heading.page, min(pages)),
                page_end=max(pages),
                text=text,
                paragraphs=paragraphs,
                sentences=sentences,
            )
        )

        stats.paragraphs += len(paragraphs)
        stats.sentences += len(sentences)
        stats.characters += len(text)
        stats.hyphen_repairs += sum(
            len(paragraph.repair_offsets) for paragraph in paragraphs
        )
        stats.hyphen_repairs_uncertain += sum(
            len(paragraph.uncertain_repair_offsets) for paragraph in paragraphs
        )

    return BookDocument(
        title=title,
        source_name=book.path.name,
        content_hash=book.content_hash,
        page_count=book.page_count,
        chapters=chapters,
        detection_style=detection.style,
        detection_confidence=detection.confidence,
        detection_warnings=list(detection.warnings),
        stats=stats,
    )


def document_to_dict(document: BookDocument) -> dict:
    """Serialise a document for the parse cache."""
    return {
        "title": document.title,
        "source_name": document.source_name,
        "content_hash": document.content_hash,
        "page_count": document.page_count,
        "detection_style": document.detection_style,
        "detection_confidence": document.detection_confidence,
        "detection_warnings": document.detection_warnings,
        "stats": asdict(document.stats),
        "chapters": [
            {
                "number": chapter.number,
                "title": chapter.title,
                "heading": chapter.heading,
                "page_start": chapter.page_start,
                "page_end": chapter.page_end,
                "text": chapter.text,
                "paragraphs": [asdict(item) for item in chapter.paragraphs],
                "sentences": [asdict(item) for item in chapter.sentences],
            }
            for chapter in document.chapters
        ],
    }


def document_from_dict(payload: dict) -> BookDocument:
    """Rebuild a document from the parse cache."""
    chapters = [
        Chapter(
            number=entry["number"],
            title=entry["title"],
            heading=entry["heading"],
            page_start=entry["page_start"],
            page_end=entry["page_end"],
            text=entry["text"],
            paragraphs=[
                Paragraph(
                    **{
                        **item,
                        "repair_offsets": tuple(item["repair_offsets"]),
                        "uncertain_repair_offsets": tuple(
                            item["uncertain_repair_offsets"]
                        ),
                    }
                )
                for item in entry["paragraphs"]
            ],
            sentences=[Sentence(**item) for item in entry["sentences"]],
        )
        for entry in payload["chapters"]
    ]
    return BookDocument(
        title=payload["title"],
        source_name=payload["source_name"],
        content_hash=payload["content_hash"],
        page_count=payload["page_count"],
        chapters=chapters,
        detection_style=payload["detection_style"],
        detection_confidence=payload["detection_confidence"],
        detection_warnings=list(payload.get("detection_warnings", [])),
        stats=IngestionStats(**payload["stats"]),
    )


def write_document(document: BookDocument, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document_to_dict(document), ensure_ascii=False), encoding="utf-8"
    )


def read_document(path: Path) -> BookDocument:
    return document_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
