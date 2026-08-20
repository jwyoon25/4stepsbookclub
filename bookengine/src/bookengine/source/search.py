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


# What an elided neighbouring paragraph is replaced with, so a model reading
# the window can tell a trimmed paragraph from one that ended there.
ELISION = "[...]"


@dataclass(frozen=True, slots=True)
class ContextWindow:
    """The prose around a quotation, for grounding an explanation."""

    chapter: int
    page: int
    before: str
    passage: str
    after: str

    def as_prompt_block(self, *, limit: int | None = None) -> str:
        """The window as it is shown to a model, with the passage marked.

        `limit` bounds the whole block. The paragraph the excerpt sits in is
        never trimmed — it is the thing being judged — so the budget comes off
        the neighbours, the previous paragraph losing its opening and the next
        one its ending, which are the ends furthest from the passage.
        """
        before, after = self.before, self.after
        if limit is not None:
            before, after = self._trimmed(limit)

        parts = []
        if before:
            parts.append(f"[previous paragraph]\n{before}")
        parts.append(f"[paragraph containing the excerpt]\n{self.passage}")
        if after:
            parts.append(f"[next paragraph]\n{after}")
        return "\n\n".join(parts)

    def _trimmed(self, limit: int) -> tuple[str, str]:
        """The neighbouring paragraphs, cut to fit whatever budget is left."""
        spare = limit - len(self.passage)
        if spare <= 0:
            return "", ""

        share = spare // 2
        return (
            _keep_end(self.before, share),
            _keep_start(self.after, spare - min(share, len(self.before))),
        )


def _keep_end(text: str, budget: int) -> str:
    """The last `budget` characters of a paragraph, marked as cut."""
    if len(text) <= budget:
        return text
    room = budget - len(ELISION) - 1
    return "" if room <= 0 else f"{ELISION} {text[-room:].lstrip()}"


def _keep_start(text: str, budget: int) -> str:
    """The first `budget` characters of a paragraph, marked as cut."""
    if len(text) <= budget:
        return text
    room = budget - len(ELISION) - 1
    return "" if room <= 0 else f"{text[:room].rstrip()} {ELISION}"


def _sentence_overlaps_repair(
    chapter: Chapter, paragraph_id: str, start: int, end: int
) -> bool:
    """Whether a passage contains a word this engine rejoined across a line.

    A rejoined word is usually right and occasionally wrong — a book that broke
    the hyphen in `self-aware` across a line is indistinguishable from one that
    broke `incomprehensible`. Excerpt ranking prefers passages with none, so
    the ones that go to print are the ones nothing was done to.
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


def context_window(
    document: BookDocument,
    occurrence: Occurrence,
    *,
    paragraphs_before: int = 1,
    paragraphs_after: int = 1,
) -> ContextWindow:
    """The paragraphs around an occurrence, for a grounded explanation."""
    return _window_around(
        document,
        chapter_number=occurrence.chapter,
        paragraph_id=occurrence.paragraph_id,
        page=occurrence.page,
        paragraphs_before=paragraphs_before,
        paragraphs_after=paragraphs_after,
    )


def context_for_locator(
    document: BookDocument,
    locator: ExcerptLocator,
    *,
    paragraphs_before: int = 1,
    paragraphs_after: int = 1,
) -> ContextWindow:
    """The paragraphs around a quotation that has already been cut.

    The generator gets its window from the occurrence it was writing about; the
    auditor has only a finished item, and a finished item carries a locator.
    Both routes land in the same function, because an auditor shown different
    source text from the writer would be checking a claim nobody made.
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
        paragraphs_before=paragraphs_before,
        paragraphs_after=paragraphs_after,
    )


def _window_around(
    document: BookDocument,
    *,
    chapter_number: int,
    paragraph_id: str,
    page: int,
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
    )
