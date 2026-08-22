"""Assembling the pool a lesson's twenty words are chosen from.

The brief's instruction is to generate far more candidates than are needed, so
that rejecting one costs nothing. This module does that, and makes one change to
how: the pool is harvested from the book rather than recalled by a model, and
the model's job is to judge it.

That change buys three things. Every candidate provably occurs in the lesson's
chapters, so the commonest failure of the naive arrangement — a plausible word
that is not in the book — disappears rather than being caught. The only book
text sent anywhere is one example sentence per word. And the model spends its
attention on the question it is actually good at, which is whether a Grade 8
student should learn `predicament`, rather than on remembering a novel.

The model-led arrangement is still available and still verified the same way,
because a word-type harvest cannot see a phrase and a book with unusual
vocabulary may defeat its ranking. It is a setting, not a rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import JobConfig, LessonConfig
from ..errors import ConfigError, StructuredResponseError
from ..llm.base import Message
from ..llm.chain import ProviderChain
from ..llm.structured import generate_structured
from ..prompts import PromptLibrary
from ..source.document import BookDocument
from ..source.search import find_occurrences
from ..source.text import normalize_term
from .harvest import WordType, harvest
from .models import RubricScore
from .schemas import CandidateList, RankedList


@dataclass(slots=True)
class Candidate:
    """One word that might be taught, with everything known about it so far."""

    term: str
    sense: str = ""
    example: str = ""
    reason: str = ""
    occurrences: int = 0
    score: RubricScore | None = None
    origin: str = "harvest"

    @property
    def normalized(self) -> str:
        return normalize_term(self.term)

    @property
    def rank(self) -> float:
        return self.score.total if self.score else 0.0


@dataclass(slots=True)
class PoolReport:
    """What the candidate stage did, for the run's audit artifact."""

    lesson: int
    harvested: int = 0
    proposed_by_model: int = 0
    rejected_not_in_range: list[str] = field(default_factory=list)
    rejected_high_risk: list[str] = field(default_factory=list)
    unscored: list[str] = field(default_factory=list)
    pool_size: int = 0

    def as_dict(self) -> dict:
        return {
            "lesson": self.lesson,
            "harvested": self.harvested,
            "proposed_by_model": self.proposed_by_model,
            "rejected_not_in_range": self.rejected_not_in_range,
            "rejected_high_risk": self.rejected_high_risk,
            "unscored": self.unscored,
            "pool_size": self.pool_size,
        }


# What the two batched generator stages may spend on their answers.
#
# The ceiling is not free. Groq's free tier charges its per-minute token
# allowance for what a request reserves — input plus `max_output_tokens` — not
# for what it uses, so an unused ceiling is still paid for on every call. Both
# stages here answer with one object per item sent, so a single number would be
# wrong at every batch size but one: it is a budget per item plus a floor for
# the model's own preamble.
#
# Measured on `openai/gpt-oss-120b`, three runs each, against fixture prose.
# Ranking twenty-five candidates answered in 2,681-3,675 tokens, which is 107
# to 147 apiece; proposing candidates ran 65 to 134 apiece and saturated a
# 3,000-token ceiling once. The budgets below sit above the worst run of each.
#
# Ranking is the tightest stage in the engine on Groq: twenty-five candidates
# is already 3,323 tokens of input, so the answer has under 4,700 to fit into.
# Batches much larger than that do not fit in a single request at all — fifty
# was refused outright with HTTP 413 — which is a limit on `rank_batch` rather
# than something a ceiling here can solve.
RANKING_TOKENS_PER_CANDIDATE = 160
RANKING_TOKENS_FLOOR = 512

CANDIDATE_TOKENS_PER_WORD = 150
CANDIDATE_TOKENS_FLOOR = 768


# What a ranking request costs on the way in, so a job can be refused before
# it spends twenty minutes discovering the same thing from an HTTP code.
#
# Fitted to measured `prompt_tokens` on `openai/gpt-oss-120b`: 2,619 at fifteen
# candidates, 3,015 at twenty, 3,323 at twenty-five. That is about 72 apiece on
# top of a fixed prompt, and the fit predicts the batch of fifty Groq refused
# — 13,762 estimated against the 13,477 it reported — which is the case worth
# predicting.
#
# Rounded up rather than down. An estimator used to refuse work should err
# towards refusing work that would have fitted, not towards letting through
# work that will not.
RANKING_INPUT_PER_CANDIDATE = 72
RANKING_INPUT_FLOOR = 1_650

# How close to a declared ceiling is close enough to say so out loud. A request
# at ninety-five percent of the limit fits today and is one longer sentence
# from not fitting.
BUDGET_WARNING_SHARE = 0.90


def ranking_request_tokens(candidates: int) -> int:
    """Everything one ranking request reserves: its prompt and its answer."""
    return (
        RANKING_INPUT_FLOOR
        + RANKING_INPUT_PER_CANDIDATE * max(candidates, 1)
        + ranking_output_tokens(candidates)
    )


def ranking_output_tokens(candidates: int) -> int:
    """The answer budget for scoring this many candidates."""
    return RANKING_TOKENS_FLOOR + RANKING_TOKENS_PER_CANDIDATE * max(candidates, 1)


def candidate_output_tokens(wanted: int) -> int:
    """The answer budget for proposing this many words."""
    return CANDIDATE_TOKENS_FLOOR + CANDIDATE_TOKENS_PER_WORD * max(wanted, 1)


def validate_generator_budget(job: JobConfig) -> list[str]:
    """Refuse a job whose largest request the generator would not accept.

    Ranking is the biggest single call this engine makes, and a provider that
    will not take it says so with an HTTP status rather than a smaller answer.
    Discovering that from an exception is a poor trade: the run has already
    built a chapter map, harvested a pool and spent minutes of a per-minute
    allowance by the time the first batch goes out.

    So it is checked here, against the ceiling the job declares for its own
    generator, before anything is called. An endpoint with no declared ceiling
    is not checked — the alternative is inventing a limit for it, which would
    refuse working jobs.

    Returns notes. Raises `ConfigError` only when the request provably does not
    fit, because that is the case no amount of patience fixes.
    """
    ceiling = job.llm.generator.max_request_tokens
    if ceiling is None:
        return []

    notes: list[str] = []
    batch = job.candidates.rank_batch
    needed = ranking_request_tokens(batch)

    if needed > ceiling:
        largest = _largest_batch_within(ceiling)
        raise ConfigError(
            f"`candidates.rank_batch` is {batch}, and scoring {batch} "
            f"candidates in one request reserves about {needed:,} tokens — "
            f"more than the {ceiling:,} {job.llm.generator.label} accepts in "
            f"one call. It would refuse every ranking batch of the run.\n"
            f"  Set `candidates.rank_batch` to {largest} or less."
        )

    if needed > ceiling * BUDGET_WARNING_SHARE:
        notes.append(
            f"Ranking {batch} candidates reserves about {needed:,} of the "
            f"{ceiling:,} tokens {job.llm.generator.label} allows in one "
            f"request. That fits, with {ceiling - needed:,} to spare — a book "
            f"whose example sentences run longer than this estimate would not. "
            f"`candidates.rank_batch` is the setting to lower."
        )

    if job.candidates.mode in {"model", "hybrid"}:
        notes.append(
            f"`candidates.mode` is {job.candidates.mode!r}, which sends "
            f"{job.candidates.chunk_characters:,} characters of the book per "
            "request. On an endpoint this size that is known not to fit — the "
            "9,000-character default alone is roughly 6,400 tokens before the "
            "answer. Harvest mode is the measured path; lower "
            "`candidates.chunk_characters` before relying on this one."
        )

    return notes


def _largest_batch_within(ceiling: int) -> int:
    """The biggest ranking batch that still fits, so the error names a fix."""
    batch = 1
    while batch < 200 and ranking_request_tokens(batch + 1) <= ceiling:
        batch += 1
    return batch


def _batched(values: list, size: int) -> list[list]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _chunk_text(document: BookDocument, chapters: range, size: int) -> list[str]:
    """The lesson's reading, in pieces small enough to prompt with.

    Split on paragraph boundaries so a chunk never ends mid-sentence: a model
    asked to find vocabulary in half a sentence will find vocabulary in half a
    sentence.
    """
    chunks: list[str] = []
    current: list[str] = []
    length = 0

    for number in chapters:
        if not document.has_chapter(number):
            continue
        chapter = document.chapter(number)
        for paragraph in chapter.paragraphs:
            text = chapter.slice(paragraph.char_start, paragraph.char_end)
            if length + len(text) > size and current:
                chunks.append("\n\n".join(current))
                current, length = [], 0
            current.append(text)
            length += len(text)

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _propose_with_model(
    document: BookDocument,
    job: JobConfig,
    lesson: LessonConfig,
    chain: ProviderChain,
    prompts: PromptLibrary,
    report: PoolReport,
) -> list[Candidate]:
    """Ask a model to read the chapters and name words worth teaching.

    Everything it names is checked against the book before it goes any further,
    and what fails that check is counted rather than quietly dropped — the count
    is the honest measure of how much this mode is guessing.
    """
    chunks = _chunk_text(document, lesson.chapters, job.candidates.chunk_characters)
    if not chunks:
        return []

    per_chunk = max(4, -(-job.candidates_per_lesson // len(chunks)))
    proposed: dict[str, Candidate] = {}

    for chunk in chunks:
        rendered = prompts.render(
            "candidates",
            audience=job.audience.label,
            book_title=job.book.title or document.title,
            count=per_chunk,
            excluded_terms=", ".join(job.exclusions.terms) or "none",
            lesson_number=lesson.lesson,
            reading_range=lesson.reading_range,
            source_text=chunk,
        )
        try:
            answer, _ = generate_structured(
                chain,
                [
                    Message(role="system", content=rendered.system),
                    Message(role="user", content=rendered.user),
                ],
                CandidateList,
                max_output_tokens=candidate_output_tokens(per_chunk),
            )
        except StructuredResponseError:
            # One unusable chunk is not a failed lesson; the harvest and the
            # other chunks still supply a pool. It is counted below.
            continue

        for entry in answer.candidates:
            key = normalize_term(entry.term)
            if not key or key in proposed:
                continue
            proposed[key] = Candidate(
                term=entry.term,
                sense=entry.sense,
                reason=entry.reason,
                origin="model",
            )

    report.proposed_by_model = len(proposed)

    kept: list[Candidate] = []
    for candidate in proposed.values():
        occurrences = find_occurrences(
            document, candidate.term, chapters=lesson.chapters
        )
        if not occurrences:
            # The model named a word the chapters do not contain. This is the
            # failure the harvest mode does not have.
            report.rejected_not_in_range.append(candidate.term)
            continue
        candidate.occurrences = len(occurrences)
        candidate.example = occurrences[0].text
        kept.append(candidate)

    return kept


def _from_harvest(entries: list[WordType]) -> list[Candidate]:
    return [
        Candidate(
            term=entry.dominant_surface,
            example=entry.example,
            occurrences=entry.total_in_range,
            origin="harvest",
        )
        for entry in entries
    ]


def _score(
    candidates: list[Candidate],
    job: JobConfig,
    lesson: LessonConfig,
    document: BookDocument,
    chain: ProviderChain,
    prompts: PromptLibrary,
    report: PoolReport,
) -> None:
    """Have the model score every candidate against the rubric.

    Scoring runs in batches because a free endpoint asked for two hundred
    scored words will truncate its reply, and a truncated reply loses the words
    at the end of the list without saying so. A batch that fails to parse leaves
    its candidates unscored and named in the report, rather than silently
    ranked last.
    """
    by_key = {candidate.normalized: candidate for candidate in candidates}

    for batch in _batched(candidates, job.candidates.rank_batch):
        listing = "\n".join(
            f"- {candidate.term}: {candidate.example.strip()[:180]}"
            for candidate in batch
        )
        rendered = prompts.render(
            "ranking",
            audience=job.audience.label,
            book_title=job.book.title or document.title,
            candidates=listing,
            reading_range=lesson.reading_range,
        )
        try:
            answer, _ = generate_structured(
                chain,
                [
                    Message(role="system", content=rendered.system),
                    Message(role="user", content=rendered.user),
                ],
                RankedList,
                max_output_tokens=ranking_output_tokens(len(batch)),
            )
        except StructuredResponseError:
            report.unscored.extend(candidate.term for candidate in batch)
            continue

        for ranked in answer.ranked:
            candidate = by_key.get(normalize_term(ranked.term))
            if candidate is None:
                continue
            candidate.score = RubricScore(
                difficulty=ranked.difficulty,
                general_utility=ranked.general_utility,
                context_quality=ranked.context_quality,
                educational_value=ranked.educational_value,
                generality=ranked.generality,
                exclusion_risk=ranked.exclusion_risk,
                note=ranked.note,
            )

    # A model that answers in the right shape but omits half the list has
    # scored half the list. Counting only the batches that failed to parse
    # would report that run as fully scored.
    missing = [
        candidate.term for candidate in candidates if candidate.score is None
    ]
    report.unscored = sorted(set(report.unscored) | set(missing))


def build_pool(
    document: BookDocument,
    job: JobConfig,
    lesson: LessonConfig,
    chain: ProviderChain,
    prompts: PromptLibrary,
) -> tuple[list[Candidate], PoolReport]:
    """The ranked pool this lesson will draw its vocabulary from."""
    report = PoolReport(lesson=lesson.lesson)
    mode = job.candidates.mode
    candidates: list[Candidate] = []

    if mode in {"harvest", "hybrid"}:
        entries = harvest(
            document,
            lesson.chapters,
            excluded=set(job.exclusions.terms),
            pool_size=job.candidates.pool_size,
        )
        report.harvested = len(entries)
        candidates.extend(_from_harvest(entries))

    if mode in {"model", "hybrid"}:
        known = {candidate.normalized for candidate in candidates}
        candidates.extend(
            candidate
            for candidate in _propose_with_model(
                document, job, lesson, chain, prompts, report
            )
            if candidate.normalized not in known
        )

    _score(candidates, job, lesson, document, chain, prompts, report)

    kept: list[Candidate] = []
    for candidate in candidates:
        if candidate.score and candidate.score.exclusion_risk > (
            job.candidates.max_exclusion_risk
        ):
            report.rejected_high_risk.append(candidate.term)
            continue
        kept.append(candidate)

    # An unscored candidate sorts below every scored one but stays in the pool:
    # it is a worse bet, not a disqualified one, and a lesson that would
    # otherwise come up short should be allowed to reach for it.
    kept.sort(key=lambda candidate: (candidate.score is None, -candidate.rank))
    pool = kept[: max(job.candidates_per_lesson, job.vocabulary_per_lesson * 2)]
    report.pool_size = len(pool)
    return pool, report
