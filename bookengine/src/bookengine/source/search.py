"""Finding where a word actually occurs, and what surrounds it.

This is the retrieval half of "LLMs propose, source text proves". A model may
say a word is worth teaching and may say which of its occurrences reads best,
but the list of occurrences is produced here, from the book, and the model
chooses from it by index. It never supplies a location and never supplies a
quotation.

The context window exists for the same reason. A model asked to explain what is
happening around a quotation will happily explain it from a half-remembered
plot summary; a model given the paragraph before, the paragraph itself, and the
paragraph after has something to be right or wrong about.
"""

from __future__ import annotations

from dataclasses import dataclass

from .document import BookDocument, Chapter
from .excerpt import ExcerptLocator
from .text import whole_word_pattern


@dataclass(frozen=True, slots=True)
class Occurrence:
    """One place a word appears, located in the book.

    `index` is the position in the list handed to a model. Choosing an
    occurrence is choosing an integer, which is the entire interface a model
    has to the book's text.
    """

    index: int
    chapter: int
    page: int
    sentence_id: str
    paragraph_id: str
    char_start: int
    char_end: int
    match_start: int
    match_end: int
    text: str
    surface: str
    has_repaired_word: bool

    @property
    def chapter_reference(self) -> str:
        return f"Chapter {self.chapter}"


# What an elided stretch of prose is replaced with, so a model reading a window
# can tell a trimmed paragraph from one that ended there.
ELISION = "[...]"

# How much book text one request may carry, in characters.
#
# The cap is not about cost — these are free endpoints — but about what a
# badly segmented book could do. Paragraph assembly rebuilds paragraphs from
# positioned lines, and a PDF that defeats it can merge six pages into one
# "paragraph"; without a bound, a single definition request would then post
# tens of thousands of characters of a copyrighted novel to a third party.
# Ingestion flags such a book, and this is the bound that holds whether or not
# anybody read the flag.
CONTEXT_CHARACTER_LIMIT = 1800


@dataclass(frozen=True, slots=True)
class ContextWindow:
    """The prose around a quotation, for grounding an explanation.

    `focus` is the span within `passage` that the window exists to be about —
    the excerpt itself. It is what survives trimming, so a bounded window is
    still a window onto the right sentence rather than the first 1,800
    characters of whatever paragraph the excerpt happened to land in.
    """

    chapter: int
    page: int
    before: str
    passage: str
    after: str
    focus: tuple[int, int] = (0, 0)

    def as_prompt_block(self, *, limit: int = CONTEXT_CHARACTER_LIMIT) -> str:
        """The window as it is shown to a model, with the passage marked.

        `limit` bounds the book's characters. The paragraph labels and the
        elision markers sit on top of it, and the focus span always survives —
        so the true ceiling is `limit` plus a fixed overhead, and the floor is
        whatever the excerpt itself measures.

        What gets cut, in order: the neighbouring paragraphs from their outer
        ends, which are furthest from the passage, and then the passage itself
        from around the focus. In an ordinary book nothing is cut at all.
        """
        passage = _around(self.passage, self.focus, limit)
        before, after = self._neighbours(max(0, limit - len(passage)))

        parts = []
        if before:
            parts.append(f"[previous paragraph]\n{before}")
        parts.append(f"[paragraph containing the excerpt]\n{passage}")
        if after:
            parts.append(f"[next paragraph]\n{after}")
        return "\n\n".join(parts)

    def _neighbours(self, spare: int) -> tuple[str, str]:
        """The paragraphs either side, cut to whatever budget is left."""
        if spare <= 0:
            return "", ""
        share = spare // 2
        return (
            _keep_end(self.before, share),
            _keep_start(self.after, spare - min(share, len(self.before))),
        )


def _around(text: str, focus: tuple[int, int], budget: int) -> str:
    """A stretch of `text` that fits `budget` and still contains `focus`.

    The focus is never sacrificed to the budget: a window that dropped the
    sentence it exists to be about would be worse than no window, because a
    model would answer from the surrounding prose and appear to have read the
    passage.
    """
    if len(text) <= budget:
        return text

    start = max(0, min(focus[0], len(text)))
    end = max(start, min(focus[1], len(text)))
    spare = max(0, budget - (end - start))

    left = max(0, start - spare // 2)
    right = min(len(text), end + spare - (start - left))

    # Cut at word boundaries, but never past the focus.
    if left > 0:
        space = text.find(" ", left)
        left = start if space == -1 else min(space + 1, start)
    if right < len(text):
        space = text.rfind(" ", 0, right)
        right = end if space == -1 else max(space, end)

    piece = text[left:right]
    if left > 0:
        piece = f"{ELISION} {piece.lstrip()}"
    if right < len(text):
        piece = f"{piece.rstrip()} {ELISION}"
    return piece


def _keep_end(text: str, budget: int) -> str:
    """The last `budget` characters of a paragraph, cut at a word boundary."""
    if len(text) <= budget:
        return text
    room = budget - len(ELISION) - 1
    if room <= 0:
        return ""
    tail = text[-room:]
    space = tail.find(" ")
    return f"{ELISION} {tail if space == -1 else tail[space + 1 :]}"


def _keep_start(text: str, budget: int) -> str:
    """The first `budget` characters of a paragraph, cut at a word boundary."""
    if len(text) <= budget:
        return text
    room = budget - len(ELISION) - 1
    if room <= 0:
        return ""
    head = text[:room]
    space = head.rfind(" ")
    return f"{head if space == -1 else head[:space]} {ELISION}"


def _sentence_overlaps_repair(
    chapter: Chapter, paragraph_id: str, start: int, end: int
) -> bool:
    """Whether a sentence contains a word this engine rejoined across a line.

    This is a preference, not a bar: excerpt ranking scores these passages down
    so the ones that go to print are the ones nothing was done to. The bar is
    `excerpt.unconfirmed_words`, which asks the narrower question — whether the
    repair was one the book itself confirmed — over the span actually chosen
    rather than over one sentence of it.
    """
    paragraph = chapter.paragraph(paragraph_id)
    return any(
        start <= paragraph.char_start + offset < end
        for offset in paragraph.repair_offsets
    )


def find_occurrences(
    document: BookDocument,
    term: str,
    *,
    chapters: range | list[int] | None = None,
    limit: int | None = None,
) -> list[Occurrence]:
    """Every whole-word occurrence of a term, restricted to the given chapters.

    Restricting by chapter is not a convenience. A lesson covers a chapter
    range, and a word taught in Lesson 2 has to be a word the student met in
    Lesson 2's reading; an occurrence from chapter 40 is not evidence for
    anything in chapters 13 to 24.
    """
    allowed = (
        document.chapter_numbers
        if chapters is None
        else [number for number in chapters if document.has_chapter(number)]
    )
    pattern = whole_word_pattern(term)
    occurrences: list[Occurrence] = []

    for number in allowed:
        chapter = document.chapter(number)
        for match in pattern.finditer(chapter.normalized):
            raw_start, raw_end = chapter.raw_span(match.start(), match.end())
            sentence = chapter.sentence_containing(raw_start)
            if sentence is None:
                continue

            occurrences.append(
                Occurrence(
                    index=len(occurrences),
                    chapter=number,
                    page=sentence.page,
                    sentence_id=sentence.id,
                    paragraph_id=sentence.paragraph_id,
                    char_start=sentence.char_start,
                    char_end=sentence.char_end,
                    match_start=raw_start,
                    match_end=raw_end,
                    text=chapter.slice(sentence.char_start, sentence.char_end),
                    surface=chapter.slice(raw_start, raw_end),
                    has_repaired_word=_sentence_overlaps_repair(
                        chapter,
                        sentence.paragraph_id,
                        sentence.char_start,
                        sentence.char_end,
                    ),
                )
            )

            if limit is not None and len(occurrences) >= limit:
                return occurrences

    return occurrences


def occurs_in_chapters(
    document: BookDocument, term: str, chapters: range | list[int]
) -> bool:
    """Whether a word occurs at all in a chapter range.

    The cheap version of `find_occurrences`, used to throw out candidate words
    before anything expensive happens to them.
    """
    return bool(find_occurrences(document, term, chapters=chapters, limit=1))


def context_for_locator(
    document: BookDocument,
    locator: ExcerptLocator,
    *,
    paragraphs_before: int = 1,
    paragraphs_after: int = 1,
) -> ContextWindow:
    """The paragraphs around a quotation, focused on the quotation itself.

    One function rather than two. There used to be a second entry point keyed
    on an occurrence, whose focus was the whole sentence — and a sentence in a
    badly segmented book has no bound, which is exactly the thing the window's
    budget exists to bound. Every caller now describes what it wants by
    locator, and a locator's span is capped by `ExcerptConfig.max_characters`.

    The generator and the auditor therefore see the same window for the same
    item, which the audit prompt already relies on: it tells the auditor the
    entry was written from these same paragraphs.
    """
    chapter = document.chapter(locator.chapter)
    paragraph = chapter.paragraph_containing(locator.char_start)
    if paragraph is None:
        raise KeyError(
            f"Chapter {locator.chapter} has no paragraph at character "
            f"{locator.char_start}."
        )
    return _window_around(
        document,
        chapter_number=locator.chapter,
        paragraph_id=paragraph.id,
        page=locator.page_start or paragraph.page_start,
        focus=(
            locator.char_start - paragraph.char_start,
            locator.char_end - paragraph.char_start,
        ),
        paragraphs_before=paragraphs_before,
        paragraphs_after=paragraphs_after,
    )


def _window_around(
    document: BookDocument,
    *,
    chapter_number: int,
    paragraph_id: str,
    page: int,
    focus: tuple[int, int],
    paragraphs_before: int,
    paragraphs_after: int,
) -> ContextWindow:
    chapter = document.chapter(chapter_number)
    position = next(
        index
        for index, paragraph in enumerate(chapter.paragraphs)
        if paragraph.id == paragraph_id
    )

    def joined(start: int, stop: int) -> str:
        return "\n\n".join(
            chapter.slice(paragraph.char_start, paragraph.char_end)
            for paragraph in chapter.paragraphs[max(0, start) : max(0, stop)]
        )

    target = chapter.paragraphs[position]
    return ContextWindow(
        chapter=chapter_number,
        page=page,
        before=joined(position - paragraphs_before, position),
        passage=chapter.slice(target.char_start, target.char_end),
        after=joined(position + 1, position + 1 + paragraphs_after),
        focus=focus,
    )
