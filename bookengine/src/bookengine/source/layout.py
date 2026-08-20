"""Turning positioned lines back into the paragraphs a reader would see.

Two things stand between extracted lines and readable prose. A book repeats its
title and its page number on every page, and those lines sit in the middle of
the text stream as if they were sentences. And a justified book breaks words
across lines, so `incompre-` and `hensible` arrive as separate lines and the
word is in the book without being findable in it.

Both fixes change the characters that later get quoted, so both are counted and
reported, and both are arranged so that the change cannot reach a quotation
unproved.

The running heads are labelled rather than deleted. Chapter detection needs
them — some books set their headings in the same margin band — but paragraph
assembly never does, so one stream serves both and `THE MAZE RUNNER 143` has no
route into a student excerpt.

The hyphen repair is a judgement call locally: a book that breaks the existing
hyphen in `self-aware` across a line looks exactly like one that breaks
`incomprehensible`. It is not a judgement call globally, because a book that
writes `self-aware` uses it whole somewhere else and never writes `selfaware`.
So both readings are looked up in the book's own vocabulary and the book
decides. Where it decides nothing, the repair is recorded as uncertain and the
passage is not quoted from at all.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from collections import Counter
from dataclasses import dataclass, field, replace

from .pdf import ExtractedBook, TextLine
from .text import normalize_for_matching, normalize_term

# A line is furniture when the same text appears on at least this share of
# pages in the same margin band. Three pages is the floor, because a two-page
# coincidence is a coincidence.
_FURNITURE_PAGE_SHARE = 0.40
_FURNITURE_MINIMUM_PAGES = 3

# How far from a page edge a line has to sit to count as margin furniture, as
# a share of page height.
_MARGIN_BAND = 0.11

# A vertical gap this many times the usual line pitch starts a new paragraph.
_PARAGRAPH_GAP_RATIO = 1.55

# A line starting this many points right of the body's left edge is indented.
_INDENT_POINTS = 4.0

# A line ending this far short of the body's right edge ended its paragraph,
# which is the only signal available across a page break.
_SHORT_LINE_POINTS = 24.0

_DIGITS = re.compile(r"\d+")
_SENTENCE_END = re.compile("[.!?][\"'”’)\\]]*$")

# The characters a typesetter breaks a word with. Kept explicit rather than
# folded, because the canonical text keeps the book's own punctuation.
_LINE_BREAK_HYPHENS = ("-", "‐", "‑", "\u00ad")

# What the book itself had to say about a word broken across a line.
#
# `extraor-` + `dinary` and `self-` + `conscious` look identical at the break:
# a hyphen, a letter before it, a lowercase letter after it. Joining is right
# for the first and destroys a word in the second. Nothing local separates
# them — but the book is not local. A novel that hyphenates `self-conscious`
# at one line ending has almost certainly set it whole somewhere else, and one
# that broke `extraordinary` has `extraordinary` elsewhere and never
# `extraor-dinary`. So the two reconstructions are looked up in the book's own
# unbroken vocabulary and the book decides.
REPAIR_JOINED = "joined"  # the closed-up form is attested elsewhere in the book
REPAIR_HYPHENATED = "hyphenated"  # the hyphen is the author's; it is kept
REPAIR_UNCERTAIN = "uncertain"  # the book attests both forms, or neither

# A word this short either side of the break is not evidence of anything, and
# looking it up mostly finds coincidences.
_MIN_LOOKUP_LENGTH = 4


@dataclass(frozen=True, slots=True)
class PageMetrics:
    """The measurements every layout decision is made against."""

    body_left: float
    body_right: float
    line_pitch: float
    body_size: float


@dataclass(frozen=True, slots=True)
class FurnitureRecord:
    """One repeated running head or folio, and how often it appeared."""

    signature: str
    band: str
    pages: int
    example: str


@dataclass(slots=True)
class FurnitureReport:
    """Which lines are page furniture rather than prose."""

    records: list[FurnitureRecord] = field(default_factory=list)
    dropped: set[tuple[int, int]] = field(default_factory=set)

    def keeps(self, page: int, index: int) -> bool:
        return (page, index) not in self.dropped

    @property
    def dropped_count(self) -> int:
        return len(self.dropped)


@dataclass(frozen=True, slots=True)
class WordRepair:
    """One word rejoined across a line break, and how sure the engine is."""

    offset: int
    kind: str
    word: str

    @property
    def certain(self) -> bool:
        """Whether the book itself settled which form was meant."""
        return self.kind != REPAIR_UNCERTAIN


@dataclass(slots=True)
class AssembledParagraph:
    """One paragraph of prose, rebuilt from its lines."""

    text: str
    page_start: int
    page_end: int
    line_count: int
    repairs: list[WordRepair] = field(default_factory=list)

    @property
    def repair_offsets(self) -> list[int]:
        return [repair.offset for repair in self.repairs]

    @property
    def uncertain_repair_offsets(self) -> list[int]:
        """Where this paragraph reads a word the book could not confirm."""
        return [repair.offset for repair in self.repairs if not repair.certain]


def page_metrics(lines: list[TextLine]) -> PageMetrics:
    """Measure the body text block from the lines themselves.

    Nothing is assumed about margins or type size: a book sets its own, and the
    only reliable description of "where the text is" is where most of it is.
    """
    if not lines:
        return PageMetrics(
            body_left=0.0, body_right=0.0, line_pitch=12.0, body_size=10.0
        )

    left_counts = Counter(round(line.x0) for line in lines)
    body_left = float(min(left_counts, key=lambda value: (-left_counts[value], value)))
    widest = sorted(line.x1 for line in lines)[-max(1, len(lines) // 5) :]
    body_right = float(statistics.median(widest))

    pitches: list[float] = []
    by_page: dict[int, list[TextLine]] = {}
    for line in lines:
        by_page.setdefault(line.page, []).append(line)
    for page_lines in by_page.values():
        ordered = sorted(page_lines, key=lambda line: line.y0)
        pitches.extend(
            second.y0 - first.y0
            for first, second in zip(ordered, ordered[1:], strict=False)
            if 0 < second.y0 - first.y0 < 100
        )

    sizes = [line.size for line in lines if line.size > 0]
    return PageMetrics(
        body_left=body_left,
        body_right=body_right,
        line_pitch=float(statistics.median(pitches)) if pitches else 12.0,
        body_size=float(statistics.median(sizes)) if sizes else 10.0,
    )


def _signature(text: str) -> str:
    """What makes two running heads "the same" head.

    Digits are masked so a folio counts as one recurring line rather than three
    hundred unique ones, and so a running head carrying the page number still
    matches itself.
    """
    return _DIGITS.sub("#", normalize_for_matching(text).upper())


def detect_furniture(book: ExtractedBook) -> FurnitureReport:
    """Find the running heads and page numbers, by repetition and position.

    Position alone would catch a chapter heading that happens to sit high on
    its page; repetition alone would catch a refrain. Requiring both is what
    keeps `CHAPTER 1` out of this, and the caller can retry without furniture
    removal if chapter detection then finds nothing.
    """
    report = FurnitureReport()
    observed: dict[tuple[str, str], list[tuple[int, int, str]]] = {}

    for page in book.pages:
        if not page.lines:
            continue
        header_limit = page.height * _MARGIN_BAND
        footer_limit = page.height * (1 - _MARGIN_BAND)
        for index, line in enumerate(page.lines):
            if line.y1 <= header_limit:
                band = "header"
            elif line.y0 >= footer_limit:
                band = "footer"
            else:
                continue
            key = (_signature(line.text), band)
            observed.setdefault(key, []).append((page.number, index, line.text))

    threshold = max(
        _FURNITURE_MINIMUM_PAGES,
        int(round(book.page_count * _FURNITURE_PAGE_SHARE)),
    )

    for (signature, band), appearances in sorted(observed.items()):
        pages = {page for page, _, _ in appearances}
        if len(pages) < threshold:
            continue
        report.records.append(
            FurnitureRecord(
                signature=signature,
                band=band,
                pages=len(pages),
                example=appearances[0][2],
            )
        )
        report.dropped.update((page, index) for page, index, _ in appearances)

    return report


def prose_lines(
    book: ExtractedBook, furniture: FurnitureReport | None = None
) -> list[TextLine]:
    """Every line that is part of the book's text, in reading order."""
    kept: list[TextLine] = []
    for page in book.pages:
        for index, line in enumerate(page.lines):
            if furniture is None or furniture.keeps(page.number, index):
                kept.append(line)
    return kept


def marked_lines(
    book: ExtractedBook, furniture: FurnitureReport
) -> list[TextLine]:
    """Every line in the book, with the page furniture labelled rather than gone.

    Chapter detection sometimes needs the running heads: a book that sets
    `CHAPTER 9` in the same margin band as its running title loses its headings
    to the strip and reads as chapterless. Quoting never needs them, and a
    student excerpt carrying `THE MAZE RUNNER 143` across a page break is a
    defect however the headings were found.

    Keeping one stream with the furniture labelled serves both. Detection reads
    the whole list, so the line indices its headings carry stay valid; the
    document is built from the labelled subset, so what a chapter is made of is
    prose either way.
    """
    return [
        replace(line, furniture=not furniture.keeps(page.number, index))
        for page in book.pages
        for index, line in enumerate(page.lines)
    ]


def build_lexicon(lines: list[TextLine]) -> frozenset[str]:
    """Every word the book sets whole on one line, in comparison form.

    This is the evidence a hyphen decision is made against, and it is built
    only from words that were never broken: the fragment before a line-ending
    hyphen is dropped, because a fragment is what is in question rather than
    what answers it.
    """
    found: set[str] = set()
    for line in lines:
        words = line.text.split()
        if words and words[-1].endswith(_LINE_BREAK_HYPHENS):
            words = words[:-1]
        for word in words:
            normalized = normalize_term(word)
            if normalized:
                found.add(normalized)
    return frozenset(found)


def classify_repair(
    tail: str, head: str, lexicon: frozenset[str]
) -> tuple[str, str]:
    """Decide what a word broken across a line was, and say how sure that is.

    Returns the kind and the word as it will now read. The two readings are
    looked up in the book's own vocabulary, and the one the book uses elsewhere
    wins. When the book uses both, or neither, nothing here is allowed to
    guess: the closed-up form is still produced, because it is right far more
    often, but the repair is marked uncertain and excerpt selection will not
    quote through it.
    """
    joined = normalize_term(tail[:-1] + head)
    hyphenated = normalize_term(tail + head)

    if min(len(joined), len(hyphenated)) < _MIN_LOOKUP_LENGTH:
        return REPAIR_UNCERTAIN, joined

    closed_up = joined in lexicon
    kept = hyphenated in lexicon

    if closed_up and not kept:
        return REPAIR_JOINED, joined
    if kept and not closed_up:
        return REPAIR_HYPHENATED, hyphenated
    return REPAIR_UNCERTAIN, joined


def _join(
    previous: str, addition: str, lexicon: frozenset[str] = frozenset()
) -> tuple[str, str | None, str]:
    """Join two lines of one paragraph, repairing a broken word if that is what
    the line break was.

    The condition is narrow on purpose: a trailing hyphen, a letter before it,
    and a lowercase letter starting the next line. A line ending in a dash used
    as punctuation, or one whose next line starts a proper noun, is left alone.

    Returns the joined text, the kind of repair, and the word that repair
    produced. The kind is `None` where the line break was just a line break.
    """
    if not (
        previous.endswith(_LINE_BREAK_HYPHENS)
        and len(previous) >= 2
        and previous[-2].isalpha()
        and addition[:1].islower()
    ):
        return f"{previous} {addition}", None, ""

    kind, word = classify_repair(
        previous.rsplit(" ", 1)[-1], addition.split(" ", 1)[0], lexicon
    )
    if kind == REPAIR_HYPHENATED:
        return previous + addition, kind, word
    return previous[:-1] + addition, kind, word


def assemble_paragraphs(
    lines: list[TextLine],
    metrics: PageMetrics,
    lexicon: frozenset[str] | None = None,
) -> list[AssembledParagraph]:
    """Group consecutive lines into paragraphs and rejoin their words.

    Three signals start a paragraph: a first-line indent, a vertical gap wider
    than the page's own line pitch, and — across a page break, where neither is
    visible — a previous line that both ended a sentence and stopped short of
    the right margin. A change of type size starts one too, which is what
    separates a chapter heading from the prose under it.

    `lexicon` is the book's own unbroken vocabulary, from `build_lexicon`, and
    it is what decides whether a word split at a line ending closes up or keeps
    its hyphen. Without one every repair is recorded as uncertain, which is the
    right answer when there is no evidence rather than a degraded one.
    """
    vocabulary = frozenset() if lexicon is None else lexicon
    paragraphs: list[AssembledParagraph] = []
    current: list[TextLine] = []

    def flush() -> None:
        if not current:
            return
        # The leading whitespace comes off before anything is measured. A strip
        # applied at the end would move every character in the paragraph left
        # and leave the recorded repair offsets pointing one word over.
        text = unicodedata.normalize("NFC", current[0].text).lstrip()
        repairs: list[WordRepair] = []
        for line in current[1:]:
            addition = unicodedata.normalize("NFC", line.text)
            text, kind, word = _join(text, addition, vocabulary)
            if kind is not None:
                repairs.append(
                    WordRepair(
                        offset=len(text) - len(addition), kind=kind, word=word
                    )
                )
        paragraphs.append(
            AssembledParagraph(
                text=text.rstrip(),
                page_start=current[0].page,
                page_end=current[-1].page,
                line_count=len(current),
                repairs=repairs,
            )
        )
        current.clear()

    for line in lines:
        if not current:
            current.append(line)
            continue

        previous = current[-1]
        indented = line.x0 > metrics.body_left + _INDENT_POINTS
        same_page = line.page == previous.page
        gapped = same_page and (
            line.y0 - previous.y0 > metrics.line_pitch * _PARAGRAPH_GAP_RATIO
        )
        ended_paragraph = (not same_page) and (
            _SENTENCE_END.search(previous.text.rstrip()) is not None
            and previous.x1 < metrics.body_right - _SHORT_LINE_POINTS
        )
        size_changed = abs(line.size - previous.size) > 0.75

        if indented or gapped or ended_paragraph or size_changed:
            flush()
        current.append(line)

    flush()
    return paragraphs
