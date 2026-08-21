"""Working out where the chapters are, or admitting that we cannot.

A wrong chapter map is the worst failure this engine has available. It does not
look like a failure: every quotation is real, every word occurs, and every
workbook row carries a chapter number that is off by one for the rest of the
book. Nothing downstream can catch it, because everything downstream trusts
this module. So detection is built to be refused rather than coaxed.

Books number chapters in at least five ways, and a table of contents lists all
of them again on page four. The approach is to try each style over the whole
book, keep only the style that produces one unbroken run of 1..N, and report a
confidence the caller is expected to act on. `ChapterDetectionError` is a normal
outcome here, not a bug.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..errors import ChapterDetectionError
from .pdf import TextLine
from .text import normalize_for_matching

# Two headings closer together than this are a contents listing, not two
# chapters. No chapter in a novel is eight lines long.
MIN_LINES_BETWEEN_CHAPTERS = 8

# A chapter with less text than this is a detection artefact, not a chapter.
MIN_CHAPTER_CHARACTERS = 400

# A heading is a short line. Prose that happens to begin "Chapter 4 was when
# everything changed" is not.
MAX_HEADING_CHARACTERS = 72

_UNITS = {
    "ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6,
    "SEVEN": 7, "EIGHT": 8, "NINE": 9, "TEN": 10, "ELEVEN": 11,
    "TWELVE": 12, "THIRTEEN": 13, "FOURTEEN": 14, "FIFTEEN": 15,
    "SIXTEEN": 16, "SEVENTEEN": 17, "EIGHTEEN": 18, "NINETEEN": 19,
}
_TENS = {
    "TWENTY": 20, "THIRTY": 30, "FORTY": 40, "FIFTY": 50, "SIXTY": 60,
    "SEVENTY": 70, "EIGHTY": 80, "NINETY": 90,
}
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}

# Lines that mean the story has ended. Text after one of these belongs to the
# book but not to any chapter a lesson can reference.
#
# `EPILOGUE` is the one of these that is still the story, and it is here for
# exactly that reason. It is not a numbered chapter, so there is no chapter
# reference that would be true of it — and without this line it runs on into
# whatever chapter precedes it. The Maze Runner's epilogue was a third of what
# ingestion called chapter 62, and its sentences were quotable, verifiable, and
# cited as chapter 62 to a student who would not find them there.
#
# Only ever consulted after the last chapter heading, so the most any entry
# here can do is shorten the final chapter.
_BACK_MATTER = (
    "ACKNOWLEDGMENTS", "ACKNOWLEDGEMENTS", "ABOUT THE AUTHOR", "AFTERWORD",
    "EPILOGUE", "APPENDIX", "GLOSSARY", "BIBLIOGRAPHY", "READING GROUP GUIDE",
    "DISCUSSION QUESTIONS", "ALSO BY",
)


def parse_number_word(text: str) -> int | None:
    """Read `TWENTY-THREE` and `Seven` as integers, and nothing else as one."""
    cleaned = text.upper().replace("-", " ").replace("AND", " ").split()
    if not cleaned or len(cleaned) > 2:
        return None
    if len(cleaned) == 1:
        word = cleaned[0]
        return _UNITS.get(word) or _TENS.get(word)
    tens, units = cleaned
    if tens in _TENS and units in _UNITS and _UNITS[units] < 10:
        return _TENS[tens] + _UNITS[units]
    return None


def parse_roman(text: str) -> int | None:
    """Read a Roman numeral, rejecting anything not in canonical form.

    Canonicality is the whole point: `I` is chapter one, but the word `I` is
    also a sentence, and requiring the numeral to round-trip keeps loose
    letters out.
    """
    candidate = text.upper().strip()
    if not candidate or any(character not in _ROMAN_VALUES for character in candidate):
        return None

    total = 0
    previous = 0
    for character in reversed(candidate):
        value = _ROMAN_VALUES[character]
        total += -value if value < previous else value
        previous = max(previous, value)

    return total if total > 0 and _to_roman(total) == candidate else None


def _to_roman(value: int) -> str:
    numerals = (
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    )
    result = []
    for amount, numeral in numerals:
        while value >= amount:
            result.append(numeral)
            value -= amount
    return "".join(result)


@dataclass(frozen=True, slots=True)
class HeadingStyle:
    """One way a book might spell a chapter heading."""

    name: str
    pattern: re.Pattern[str]
    read: str  # "arabic" | "word" | "roman"


# `\s*` rather than `\s+` after CHAPTER so `CHAPTER1` from a tight PDF still
# reads. The separator before a title accepts the punctuation books use and a
# bare space, because plenty of them use nothing at all.
_TITLE = r"(?:\s*[:.–—-]\s*(?P<title>.{1,60}))?"

HEADING_STYLES = (
    HeadingStyle(
        "chapter-arabic",
        re.compile(rf"^CHAPTER\s*(?P<value>\d{{1,3}}){_TITLE}$", re.IGNORECASE),
        "arabic",
    ),
    HeadingStyle(
        "chapter-word",
        re.compile(
            rf"^CHAPTER\s*(?P<value>[A-Za-z]+(?:[-\s][A-Za-z]+)?){_TITLE}$",
            re.IGNORECASE,
        ),
        "word",
    ),
    HeadingStyle(
        "chapter-roman",
        re.compile(rf"^CHAPTER\s*(?P<value>[IVXLC]+){_TITLE}$", re.IGNORECASE),
        "roman",
    ),
    HeadingStyle("bare-arabic", re.compile(r"^(?P<value>\d{1,3})$"), "arabic"),
    HeadingStyle(
        "bare-word", re.compile(r"^(?P<value>[A-Za-z]+(?:[-\s][A-Za-z]+)?)$"), "word"
    ),
    HeadingStyle("bare-roman", re.compile(r"^(?P<value>[IVXLC]+)$"), "roman"),
)


@dataclass(frozen=True, slots=True)
class ChapterHeading:
    """One accepted chapter heading and where it sits in the line stream."""

    number: int
    title: str | None
    raw: str
    line_index: int
    page: int
    starts_page: bool


@dataclass(slots=True)
class ChapterDetection:
    """What detection concluded, and how sure it is.

    `issues` are blockers: the chapter map is wrong or unknowable and no
    operator assurance can make it usable. `warnings` are things that are
    merely unusual — a book whose chapters run on without a page break, say —
    which a human-supplied chapter count is allowed to clear.
    """

    style: str | None
    headings: list[ChapterHeading]
    confidence: str
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    considered: dict[str, int] = field(default_factory=dict)
    back_matter_line: int | None = None

    @property
    def numbers(self) -> list[int]:
        return [heading.number for heading in self.headings]

    @property
    def count(self) -> int:
        return len(self.headings)


def _read_value(style: HeadingStyle, raw: str) -> int | None:
    if style.read == "arabic":
        return int(raw) if raw.isdigit() else None
    if style.read == "word":
        return parse_number_word(raw)
    return parse_roman(raw)


def _candidates(
    lines: list[TextLine], style: HeadingStyle
) -> list[tuple[int, int, str | None, str]]:
    """Every line this style would read as a heading, in document order."""
    found: list[tuple[int, int, str | None, str]] = []
    page_first_line: dict[int, int] = {}
    for index, line in enumerate(lines):
        page_first_line.setdefault(line.page, index)

    for index, line in enumerate(lines):
        text = normalize_for_matching(line.text)
        if not text or len(text) > MAX_HEADING_CHARACTERS:
            continue
        match = style.pattern.match(text)
        if match is None:
            continue
        number = _read_value(style, match.group("value"))
        if number is None or not 1 <= number <= 200:
            continue
        title = (match.groupdict().get("title") or "").strip() or None
        found.append((index, number, title, line.text))

    return found


def _contents_clusters(
    candidates: list[tuple[int, int, str | None, str]],
) -> set[int]:
    """Find the candidate positions that belong to a contents listing.

    A book lists every chapter it has on page four, and each of those lines
    reads exactly like the heading it points at. What separates the two is
    spacing: a contents entry has another entry a line below it, and a chapter
    heading has a chapter under it. Three or more candidates packed together is
    a listing, and the whole run is discarded — including its last entry, which
    would otherwise crowd the book's real first heading out of the running.
    """
    listed: set[int] = set()
    cluster = [0] if candidates else []

    for position in range(1, len(candidates)):
        index, number = candidates[position][0], candidates[position][1]
        previous_index, previous_number = (
            candidates[position - 1][0],
            candidates[position - 1][1],
        )
        # A listing runs close together *and* counts upward. The step down from
        # the last contents entry to the book's own first heading is the
        # boundary between the two, and without it the real Chapter 1 — which
        # follows the listing within a line or two — would be swept up with it.
        continues = (
            index - previous_index < MIN_LINES_BETWEEN_CHAPTERS
            and number > previous_number
        )
        if continues:
            cluster.append(position)
            continue
        if len(cluster) >= 3:
            listed.update(cluster)
        cluster = [position]

    if len(cluster) >= 3:
        listed.update(cluster)

    return listed


def _select_run(
    candidates: list[tuple[int, int, str | None, str]],
    lines: list[TextLine],
) -> list[ChapterHeading]:
    """Keep the candidates that form one unbroken 1..N run through the book.

    Contents listings go first, as whole blocks. What survives is walked in
    document order, accepting only the next number expected and only when
    enough text has passed since the last accepted heading to have been a
    chapter. A half-title repeating `CHAPTER 1` a page early therefore costs
    nothing: the second occurrence is not the number expected by then.
    """
    listed = _contents_clusters(candidates)
    page_first_line: dict[int, int] = {}
    for index, line in enumerate(lines):
        page_first_line.setdefault(line.page, index)

    accepted: list[ChapterHeading] = []
    expected = 1

    for position, (index, number, title, raw) in enumerate(candidates):
        if position in listed or number != expected:
            continue
        if accepted and index - accepted[-1].line_index < MIN_LINES_BETWEEN_CHAPTERS:
            continue
        page = lines[index].page
        accepted.append(
            ChapterHeading(
                number=number,
                title=title,
                raw=raw,
                line_index=index,
                page=page,
                starts_page=page_first_line.get(page) == index,
            )
        )
        expected += 1

    return accepted


def _back_matter_line(lines: list[TextLine], after: int) -> int | None:
    for index in range(after, len(lines)):
        text = normalize_for_matching(lines[index].text).upper()
        if len(text) <= MAX_HEADING_CHARACTERS and text.startswith(_BACK_MATTER):
            return index
    return None


def detect_chapters(lines: list[TextLine]) -> ChapterDetection:
    """Try every heading style and report the one that holds together.

    The result is advisory. Nothing here raises; the caller decides what a
    `low` confidence is worth, and `require_confident_detection` is what turns
    it into a refusal.
    """
    considered: dict[str, int] = {}
    best: tuple[HeadingStyle, list[ChapterHeading]] | None = None

    for style in HEADING_STYLES:
        run = _select_run(_candidates(lines, style), lines)
        considered[style.name] = len(run)
        if best is None or len(run) > len(best[1]):
            best = (style, run)

    if best is None or not best[1]:
        return ChapterDetection(
            style=None,
            headings=[],
            confidence="none",
            issues=["No chapter headings were recognised in any known style."],
            considered=considered,
        )

    style, headings = best
    issues: list[str] = []
    warnings: list[str] = []

    if len(headings) < 2:
        issues.append(
            f"Only {len(headings)} chapter heading was recognised, using the "
            f"{style.name} style."
        )

    runners_up = sorted(
        (count for name, count in considered.items() if name != style.name),
        reverse=True,
    )
    if runners_up and runners_up[0] >= len(headings):
        issues.append(
            "Two heading styles explain the book equally well, so the chapter "
            "map is ambiguous."
        )

    off_page = [heading.number for heading in headings if not heading.starts_page]
    if len(off_page) > len(headings) / 2:
        warnings.append(
            f"{len(off_page)} of {len(headings)} headings do not start a page. "
            "That is normal in some books and a sign of a misread heading in "
            "others."
        )

    if issues:
        confidence = "low"
    elif warnings:
        confidence = "acceptable"
    else:
        confidence = "high"

    return ChapterDetection(
        style=style.name,
        headings=headings,
        confidence=confidence,
        issues=issues,
        warnings=warnings,
        considered=considered,
        back_matter_line=_back_matter_line(lines, headings[-1].line_index + 1),
    )


def require_confident_detection(
    detection: ChapterDetection,
    *,
    book_name: str,
    expected_chapters: int | None = None,
) -> None:
    """Turn a shaky chapter map into a refusal, with the numbers that caused it.

    `expected_chapters` is the operator's own count, read off the book's
    contents page. It is the most valuable check available here, because it is
    the one fact about the book that the PDF cannot supply about itself — and
    it is the only thing allowed to clear a warning. It cannot clear a blocker:
    agreeing with a chapter count says nothing about a chapter map that two
    different heading styles explain equally well.
    """
    blockers = list(detection.issues)

    if expected_chapters is not None and detection.count != expected_chapters:
        blockers.append(
            f"The job expects {expected_chapters} chapters and detection found "
            f"{detection.count}."
        )
    elif expected_chapters is None and detection.warnings:
        blockers.extend(detection.warnings)
        blockers.append(
            "Set `book.expected_chapters` in the job configuration to confirm "
            "the count by hand, once you have checked the ingestion report."
        )

    if not blockers:
        return

    detail = "\n".join(f"  - {problem}" for problem in blockers)
    considered = ", ".join(
        f"{name}: {count}" for name, count in sorted(detection.considered.items())
    )
    raise ChapterDetectionError(
        f"Chapter detection is not confident enough to generate against "
        f"{book_name}.\n"
        f"Detected chapters: {detection.count}"
        f"{f' (style: {detection.style})' if detection.style else ''}\n"
        f"{detail}\n"
        f"Styles considered: {considered}\n"
        "Generation aborted rather than risk putting the wrong chapter number "
        "on a workbook page."
    )
