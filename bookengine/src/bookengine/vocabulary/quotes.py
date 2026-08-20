"""Choosing which occurrence of a word to teach from, and cutting it out.

This is the module the whole design exists to make possible. A word has been
proposed; the book has been searched; there are now, say, nine sentences in the
lesson's chapters that contain it. Something has to pick one and produce the
quotation.

The picking is allowed to involve a model — judging which sentence teaches a
word best is a genuinely subjective call. The producing is not. A model sees a
numbered list and returns a number. The quotation is then cut from the book at
the offsets that number refers to. There is no step in which text travels from
the model into the workbook, which is why there is no step at which a
fabricated quotation has to be detected.

The deterministic pre-score exists so that the model's job is small. Ranking
nine plausible sentences is a reasonable question to ask; finding the one usable
sentence among two hundred is not, and would waste the context on sentences that
were never eligible.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..config import ExcerptConfig
from ..source.document import BookDocument
from ..source.excerpt import (
    ExcerptError,
    ExcerptLocator,
    excerpt_for_cell,
    locator_from_sentences,
)
from ..source.search import Occurrence, find_occurrences
from ..source.text import contains_whole_word

# A sentence opening on a bare pronoun refers to something the student cannot
# see, so it teaches the word less well than one that stands on its own.
_WEAK_OPENING = re.compile(
    r"^(he|she|it|they|him|her|them|his|their|that|this|those|these)\b",
    re.IGNORECASE,
)

# Capitalised words mid-sentence are usually names. A passage thick with them
# is a passage about who, not about what the word means.
_MID_SENTENCE_CAPITAL = re.compile(r"(?<=[a-z,;:] )[A-Z][a-z]{2,}")

# How many occurrences a model is ever shown. Beyond this the list stops being
# a choice and starts being a search, and the deterministic score is a better
# filter than a longer prompt.
SHORTLIST_SIZE = 8


@dataclass(slots=True)
class ExcerptCandidate:
    """One usable quotation for one word, with the reasoning behind its rank."""

    occurrence: Occurrence
    locator: ExcerptLocator
    text: str
    score: float
    notes: list[str] = field(default_factory=list)

    @property
    def chapter(self) -> int:
        return self.locator.chapter


def _sentences_from(document: BookDocument, occurrence: Occurrence) -> list:
    """The occurrence's sentence and the ones after it in the same paragraph."""
    chapter = document.chapter(occurrence.chapter)
    start = next(
        index
        for index, sentence in enumerate(chapter.sentences)
        if sentence.id == occurrence.sentence_id
    )
    run = [chapter.sentences[start]]
    for sentence in chapter.sentences[start + 1 :]:
        if sentence.paragraph_id != occurrence.paragraph_id:
            break
        run.append(sentence)
    return run


def build_excerpt(
    document: BookDocument, occurrence: Occurrence, config: ExcerptConfig
) -> ExcerptCandidate | None:
    """Grow an excerpt out from one occurrence, or decide there isn't one.

    An excerpt starts as the sentence the word is in. If that sentence is too
    short to carry any meaning it takes in the next one, and the next, up to the
    configured limits — but only within the same paragraph, because a quotation
    that jumps a scene break reads as two fragments.

    A sentence longer than the limit is refused rather than trimmed. Trimming
    would produce a passage that is not a sentence in the book, and the point of
    this engine is that everything it prints is.
    """
    run = _sentences_from(document, occurrence)

    chosen: list = []
    for sentence in run[: config.max_sentences]:
        candidate = [*chosen, sentence]
        length = candidate[-1].char_end - candidate[0].char_start
        if length > config.max_characters:
            break
        chosen = candidate
        if length >= config.min_characters:
            break

    if not chosen:
        return None

    length = chosen[-1].char_end - chosen[0].char_start
    if not config.min_characters <= length <= config.max_characters:
        return None

    try:
        locator = locator_from_sentences(
            document, occurrence.chapter, [sentence.id for sentence in chosen]
        )
    except (ExcerptError, KeyError):
        return None

    text = excerpt_for_cell(document, locator)
    if not contains_whole_word(text, occurrence.surface):
        return None

    notes: list[str] = []
    score = 0.0

    # A passage that sits comfortably inside the length band reads best in the
    # workbook's vocabulary panel; the extremes are usable but worse.
    span = config.max_characters - config.min_characters
    middle = config.min_characters + span / 2
    score += 2.0 * (1.0 - min(1.0, abs(length - middle) / max(span / 2, 1.0)))

    if occurrence.has_repaired_word:
        if config.prefer_unrepaired:
            score -= 3.0
        notes.append("contains a word rejoined across a line break")

    if _WEAK_OPENING.match(text.lstrip("\"'“‘")):
        score -= 1.5
        notes.append("opens on a pronoun, so it leans on the sentence before it")

    names = len(_MID_SENTENCE_CAPITAL.findall(text))
    if names >= 3:
        score -= 1.0
        notes.append(f"carries {names} proper nouns")

    # The word doing its work in the middle of a sentence shows more of how it
    # behaves than the same word ending one.
    relative = (occurrence.match_start - locator.char_start) / max(length, 1)
    if 0.15 <= relative <= 0.85:
        score += 1.0
    else:
        notes.append("the word sits at the very edge of the passage")

    words = len(text.split())
    if words < 8:
        score -= 1.0
        notes.append("very short")

    if len(chosen) > 1:
        score -= 0.25
        notes.append(f"{len(chosen)} sentences")

    return ExcerptCandidate(
        occurrence=occurrence, locator=locator, text=text, score=score, notes=notes
    )


def excerpt_candidates(
    document: BookDocument,
    term: str,
    chapters: range | list[int],
    config: ExcerptConfig,
    *,
    shortlist: int = SHORTLIST_SIZE,
) -> list[ExcerptCandidate]:
    """Every usable quotation for a word in a chapter range, best first."""
    candidates = [
        candidate
        for occurrence in find_occurrences(document, term, chapters=chapters)
        if (candidate := build_excerpt(document, occurrence, config)) is not None
    ]
    candidates.sort(key=lambda candidate: -candidate.score)
    return candidates[:shortlist]


def render_shortlist(candidates: list[ExcerptCandidate]) -> str:
    """The numbered list a model chooses from.

    Deliberately carries no chapter numbers and no offsets. A model that cannot
    see them cannot be tempted to report them, and everything it might report
    would be ignored in favour of the locator anyway.
    """
    return "\n\n".join(
        f"[{index}] {candidate.text}" for index, candidate in enumerate(candidates)
    )


Chooser = Callable[[str, list[ExcerptCandidate]], int]


def choose_excerpt(
    document: BookDocument,
    term: str,
    chapters: range | list[int],
    config: ExcerptConfig,
    *,
    chooser: Chooser | None = None,
) -> ExcerptCandidate | None:
    """Pick the quotation this word will be taught from.

    Without a `chooser` the highest deterministic score wins, which is what the
    tests and any offline run use. With one, the model picks from the shortlist
    by index — and an index outside the list, which free models do return, falls
    back to the deterministic choice rather than failing the item. A bad ranking
    is a worse workbook; a bad index is not an integrity problem, because the
    text still comes from the book either way.
    """
    candidates = excerpt_candidates(document, term, chapters, config)
    if not candidates:
        return None
    if chooser is None:
        return candidates[0]

    try:
        index = chooser(term, candidates)
    except Exception:  # noqa: BLE001 - a ranking failure must not lose the word
        return candidates[0]

    if not isinstance(index, int) or not 0 <= index < len(candidates):
        return candidates[0]
    return candidates[index]
