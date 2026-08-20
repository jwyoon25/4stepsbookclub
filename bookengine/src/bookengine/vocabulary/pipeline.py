"""The run: candidates in, verified workbook rows out, or an honest failure.

The shape of this module is dictated by one requirement — a lesson asked for
twenty words produces twenty words or the run does not claim success. That turns
what looks like a linear pipeline into a loop. An item can die at four different
points after being chosen, and each death has to be replaced from the pool and
put through every stage again, because a replacement is a new word and inherits
nothing from the one it replaced.

The four deaths, in order: no usable passage in the lesson's chapters; the
excerpt fails deterministic verification; the entry text cannot be drafted; the
independent audit rejects it. Only the fourth involves a judgement. The other
three are code refusing to pretend.

What this module does not do is lower the bar when the pool runs out. It stops,
and says which lesson, how far it got, and what the rejections were.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..config import JobConfig, LessonConfig
from ..errors import StructuredResponseError
from ..llm.base import Message
from ..llm.chain import ProviderChain
from ..llm.structured import generate_structured
from ..prompts import PromptLibrary
from ..source.document import BookDocument
from ..source.search import find_occurrences
from .audit import AUDIT_BATCH, apply_verdicts, audit_batch
from .candidates import Candidate, PoolReport, build_pool
from .dedupe import DuplicateRegistry, build_lemmatizer
from .entries import apply_draft, draft_entry
from .models import Status, VocabularyItem
from .quotes import ExcerptCandidate, choose_excerpt, render_shortlist
from .schemas import OccurrenceChoice
from .verify import FinalReport, assign_orders, final_verification, verify_item

# A lesson gets this many passes at filling itself before the pool is declared
# exhausted. Each pass is a full round of excerpt, entry, and audit for however
# many words are still missing.
MAX_ROUNDS = 6


@dataclass(slots=True)
class RunStats:
    """What the run cost and what it did, for the audit artifact."""

    started_at: str = ""
    finished_at: str = ""
    generator_labels: list[str] = field(default_factory=list)
    auditor_labels: list[str] = field(default_factory=list)
    audit_is_independent: bool = True
    lemmatizer: str = ""
    dedupe_policy: str = ""
    llm_calls: int = 0
    cache_hits: int = 0
    replacements: int = 0
    rounds: dict[int, int] = field(default_factory=dict)
    pools: list[dict] = field(default_factory=list)
    duplicates_blocked: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "generator": self.generator_labels,
            "auditor": self.auditor_labels,
            "audit_is_independent": self.audit_is_independent,
            "lemmatizer": self.lemmatizer,
            "dedupe_policy": self.dedupe_policy,
            "llm_calls": self.llm_calls,
            "cache_hits": self.cache_hits,
            "replacements": self.replacements,
            "rounds_per_lesson": self.rounds,
            "candidate_pools": self.pools,
            "duplicates_blocked": self.duplicates_blocked,
        }


@dataclass(slots=True)
class RunResult:
    """Everything one run produced."""

    items: list[VocabularyItem]
    report: FinalReport
    stats: RunStats

    @property
    def ready(self) -> list[VocabularyItem]:
        return [item for item in self.items if item.status is Status.READY]

    @property
    def ok(self) -> bool:
        return self.report.ok


class Progress:
    """Where a run says what it is doing. Replaced by the CLI's own reporter."""

    def stage(self, name: str, detail: str = "") -> None:  # pragma: no cover
        pass

    def note(self, message: str) -> None:  # pragma: no cover
        pass


def _occurrence_chooser(
    job: JobConfig,
    document: BookDocument,
    chain: ProviderChain,
    prompts: PromptLibrary,
    sense: str,
):
    """A chooser that asks a model which passage teaches the word best.

    It returns an index into a list this engine built. A model that answers with
    a number outside the list, or does not answer at all, costs the run a better
    ranking and nothing else: `choose_excerpt` falls back to the deterministic
    order and the quotation is cut from the book either way.
    """

    def choose(term: str, candidates: list[ExcerptCandidate]) -> int:
        if len(candidates) == 1:
            return 0
        rendered = prompts.render(
            "occurrence",
            audience=job.audience.label,
            book_title=job.book.title or document.title,
            occurrences=render_shortlist(candidates),
            sense=sense or "not specified",
            term=term,
        )
        answer, _ = generate_structured(
            chain,
            [
                Message(role="system", content=rendered.system),
                Message(role="user", content=rendered.user),
            ],
            OccurrenceChoice,
        )
        return answer.index

    return choose


def _attach_excerpt(
    document: BookDocument,
    job: JobConfig,
    item: VocabularyItem,
    lesson: LessonConfig,
    chain: ProviderChain,
    prompts: PromptLibrary,
    sense: str,
) -> bool:
    """Find this word's passage and put the book's own words on the item."""
    chosen = choose_excerpt(
        document,
        item.term,
        lesson.chapters,
        job.excerpt,
        chooser=_occurrence_chooser(job, document, chain, prompts, sense),
    )
    if chosen is None:
        item.fail(
            f"No usable passage for {item.term!r} in {lesson.reading_range}: every "
            "occurrence sits in a sentence outside the excerpt length limits, "
            "crossing a paragraph break, or reading a word rejoined across a "
            "line break in a form the book does not confirm."
        )
        return False

    item.locator = chosen.locator
    item.excerpt = chosen.text
    occurrences = find_occurrences(document, item.term, chapters=lesson.chapters)
    item.provenance.sentence_ids = chosen.locator.sentence_ids
    item.provenance.pages = tuple(
        range(chosen.locator.page_start, chosen.locator.page_end + 1)
    )
    item.provenance.occurrence_count = len(occurrences)
    item.provenance.occurrence_index = chosen.occurrence.index
    item.transition(Status.SOURCE_VERIFIED, "An excerpt was cut from the book.")
    return True


def _draft(
    document: BookDocument,
    job: JobConfig,
    item: VocabularyItem,
    lesson: LessonConfig,
    chain: ProviderChain,
    prompts: PromptLibrary,
    sense: str,
) -> bool:
    occurrences = find_occurrences(document, item.term, chapters=lesson.chapters)
    if not occurrences:
        item.fail(f"{item.term!r} no longer occurs in {lesson.reading_range}.")
        return False

    chosen = occurrences[
        min(item.provenance.occurrence_index or 0, len(occurrences) - 1)
    ]
    try:
        draft, completion = draft_entry(
            document, job, item, chosen, chain, prompts, sense=sense
        )
    except StructuredResponseError as failure:
        item.fail(f"The definition could not be written: {failure}")
        return False

    apply_draft(item, draft, completion)
    item.transition(Status.GENERATED, "Definition, meaning, and context written.")
    return True


def build_lesson(
    document: BookDocument,
    job: JobConfig,
    lesson: LessonConfig,
    pool: list[Candidate],
    registry: DuplicateRegistry,
    generator: ProviderChain,
    auditor: ProviderChain,
    prompts: PromptLibrary,
    stats: RunStats,
    progress: Progress,
) -> list[VocabularyItem]:
    """Fill one lesson, replacing what fails until the pool is spent."""
    target = job.vocabulary_per_lesson
    remaining = list(pool)
    produced: list[VocabularyItem] = []
    ready: list[VocabularyItem] = []
    rounds = 0

    while len(ready) < target and remaining and rounds < MAX_ROUNDS:
        rounds += 1
        needed = target - len(ready)
        batch: list[tuple[VocabularyItem, str]] = []

        while remaining and len(batch) < needed:
            candidate = remaining.pop(0)
            clash = registry.conflict(candidate.term, lesson=lesson.lesson)
            if clash is not None:
                registry.record_block(clash)
                continue

            item = VocabularyItem(
                lesson=lesson.lesson,
                term=candidate.term,
                normalized_term=candidate.normalized,
                score=candidate.score,
            )
            item.provenance.source_name = document.source_name
            item.provenance.content_hash = document.content_hash
            registry.claim(candidate.term, lesson=lesson.lesson)
            batch.append((item, candidate.sense))
            produced.append(item)

        if not batch:
            break

        progress.stage(
            f"Lesson {lesson.lesson}",
            f"round {rounds}: {len(batch)} candidate(s), {len(ready)}/{target} ready",
        )

        surviving: list[VocabularyItem] = []
        for item, sense in batch:
            if not _attach_excerpt(
                document, job, item, lesson, generator, prompts, sense
            ):
                registry.release(item.term, lesson=lesson.lesson)
                continue
            if not _draft(document, job, item, lesson, generator, prompts, sense):
                registry.release(item.term, lesson=lesson.lesson)
                continue
            item.transition(Status.AUDIT_PENDING, "Sent for independent audit.")
            surviving.append(item)

        for start in range(0, len(surviving), AUDIT_BATCH):
            chunk = surviving[start : start + AUDIT_BATCH]
            passed, failed = apply_verdicts(
                chunk, audit_batch(chunk, job, document, auditor, prompts)
            )
            for item in failed:
                registry.release(item.term, lesson=lesson.lesson)
                stats.replacements += 1

            for item in passed:
                verification = verify_item(document, job, item)
                if not verification.ok:
                    reason = (
                        verification.reasons[0]
                        if verification.reasons
                        else "verification failed"
                    )
                    item.fail(reason)
                    registry.release(item.term, lesson=lesson.lesson)
                    stats.replacements += 1
                    continue
                item.mark_ready(verification, "Verified against the book and audited.")
                ready.append(item)

    stats.rounds[lesson.lesson] = rounds
    return produced


def run_job(
    document: BookDocument,
    job: JobConfig,
    generator: ProviderChain,
    auditor: ProviderChain,
    prompts: PromptLibrary,
    *,
    progress: Progress | None = None,
) -> RunResult:
    """Generate the whole book's vocabulary and prove it before returning."""
    progress = progress or Progress()
    lemmatizer = build_lemmatizer()
    registry = DuplicateRegistry(job.dedupe, lemmatizer=lemmatizer)

    stats = RunStats(
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
        generator_labels=generator.labels,
        auditor_labels=auditor.labels,
        audit_is_independent=job.llm.audit_is_independent,
        lemmatizer=lemmatizer.name,
        dedupe_policy=registry.policy_note,
    )

    items: list[VocabularyItem] = []
    for lesson in sorted(job.lessons, key=lambda entry: entry.lesson):
        progress.stage(f"Lesson {lesson.lesson}", "building the candidate pool")
        pool, pool_report = build_pool(document, job, lesson, generator, prompts)
        stats.pools.append(pool_report.as_dict())
        _warn_thin_pool(pool_report, job, lesson, progress)

        items.extend(
            build_lesson(
                document,
                job,
                lesson,
                pool,
                registry,
                generator,
                auditor,
                prompts,
                stats,
                progress,
            )
        )

    assign_orders(items)
    report = final_verification(document, job, items)
    # Ordering is assigned before the final pass and re-assigned after it,
    # because an item demoted during final verification would otherwise leave a
    # gap in a lesson's numbering.
    assign_orders(items)

    stats.duplicates_blocked = list(registry.blocked)
    stats.llm_calls = generator.calls + auditor.calls
    stats.cache_hits = generator.cache_hits + auditor.cache_hits
    stats.finished_at = datetime.now(UTC).isoformat(timespec="seconds")

    return RunResult(items=items, report=report, stats=stats)


def _warn_thin_pool(
    pool: PoolReport, job: JobConfig, lesson: LessonConfig, progress: Progress
) -> None:
    if pool.pool_size < job.vocabulary_per_lesson * 2:
        progress.note(
            f"Lesson {lesson.lesson}: the candidate pool is {pool.pool_size} for "
            f"{job.vocabulary_per_lesson} words. There is little room to replace "
            "a rejected item."
        )
    if pool.rejected_not_in_range:
        progress.note(
            f"Lesson {lesson.lesson}: {len(pool.rejected_not_in_range)} "
            "model-proposed word(s) were discarded because they do not occur in "
            "the lesson's chapters."
        )
    if pool.unscored:
        progress.note(
            f"Lesson {lesson.lesson}: {len(pool.unscored)} candidate(s) could not "
            "be scored and were ranked below every scored candidate."
        )
