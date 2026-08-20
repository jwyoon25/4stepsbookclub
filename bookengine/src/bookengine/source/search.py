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


@dataclass(frozen=True, slots=True)
class ContextWindow:
    """The prose around a quotation, for grounding an explanation."""

    chapter: int
    page: int
    before: str
    passage: str
    after: str

    def as_prompt_block(self) -> str:
        """The window as it is shown to a model, with the passage marked."""
        parts = []
        if self.before:
            parts.append(f"[previous paragraph]\n{self.before}")
        parts.append(f"[paragraph containing the excerpt]\n{self.passage}")
        if self.after:
            parts.append(f"[next paragraph]\n{self.after}")
        return "\n\n".join(parts)


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
    chapter = document.chapter(occurrence.chapter)
    position = next(
        index
        for index, paragraph in enumerate(chapter.paragraphs)
        if paragraph.id == occurrence.paragraph_id
    )

    def joined(start: int, stop: int) -> str:
        return "\n\n".join(
            chapter.slice(paragraph.char_start, paragraph.char_end)
            for paragraph in chapter.paragraphs[max(0, start) : max(0, stop)]
        )

    target = chapter.paragraphs[position]
    return ContextWindow(
        chapter=occurrence.chapter,
        page=occurrence.page,
        before=joined(position - paragraphs_before, position),
        passage=chapter.slice(target.char_start, target.char_end),
        after=joined(position + 1, position + 1 + paragraphs_after),
    )
