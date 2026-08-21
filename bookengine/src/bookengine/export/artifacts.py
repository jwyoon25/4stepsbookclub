"""The record of what a run actually did, next to the rows it produced.

The TSV says what to paste. It cannot say which book was read, which model
wrote a definition, which of a word's occurrences was chosen, or how many
candidates were thrown away to get twenty words. Someone will ask — usually
about one row, months later, when the only evidence left is what was written
down at the time.

So two files sit beside the paste block. `vocabulary.json` is the machine-
readable twin of the TSV: the same rows, in the same order, each carrying its
full provenance. `audit.json` is the run's account of itself: every item
including the ones that failed, and a summary whose numbers are recomputed here
from the job, the book and the items rather than accumulated by the pipeline
that is being reported on. A counter incremented by the code under scrutiny is
not evidence; a count taken from the finished items is.

Nothing here decides whether a run succeeded. It reports, in numbers a person
can check, and leaves the verdict to the caller.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from ..config import JobConfig
from ..source.document import BookDocument
from ..vocabulary.audit import independence_of, weakest_independence
from ..vocabulary.dedupe import conflicts_among
from ..vocabulary.models import Status, VocabularyItem
from .tsv import exportable_items, vocabulary_rows
from .workbook_contract import VOCABULARY_COLUMNS


def write_vocabulary_json(
    items: list[VocabularyItem],
    path: Path,
    *,
    job: JobConfig,
    document: BookDocument,
) -> Path:
    """Write the exported rows with everything the TSV had to leave out.

    The cells come from `vocabulary_rows`, so this file cannot describe a row
    the TSV refused to write: the same contract checks run, and they raise here
    too. `rows[n]` and `items[n]` are the same item, which is what lets a
    reader go from a cell in the Sheet to the sentence it was cut from.
    """
    exported = exportable_items(items)
    payload = {
        "generated_at": _timestamp(),
        "book": _book_summary(document),
        "job": _job_summary(job),
        "columns": list(VOCABULARY_COLUMNS),
        "rows": vocabulary_rows(items),
        "items": [item.as_dict() for item in exported],
    }
    return _write_json(path, payload)


def write_audit_json(
    items: list[VocabularyItem],
    path: Path,
    *,
    job: JobConfig,
    document: BookDocument,
    run: dict,
) -> Path:
    """Write the summary together with every item the run touched.

    Failed and replaced candidates are in here and nowhere else. A summary
    saying eleven candidates were rejected is only useful if the eleven can be
    read, which is how a bad prompt gets found.
    """
    payload = build_audit_summary(items, job=job, document=document, run=run)
    payload["items"] = [item.as_dict() for item in _stable_order(items)]
    return _write_json(path, payload)


def build_audit_summary(
    items: list[VocabularyItem],
    *,
    job: JobConfig,
    document: BookDocument,
    run: dict,
) -> dict:
    """Count what happened, from the items rather than from the pipeline."""
    exported = exportable_items(items)
    ready_by_lesson = Counter(item.lesson for item in exported)
    seen_by_lesson = Counter(item.lesson for item in items)

    per_lesson = [
        {
            "lesson": lesson.lesson,
            "reading_range": lesson.reading_range,
            "requested": job.vocabulary_per_lesson,
            "ready": ready_by_lesson[lesson.lesson],
            "candidates_seen": seen_by_lesson[lesson.lesson],
        }
        for lesson in sorted(job.lessons, key=lambda entry: entry.lesson)
    ]
    shortfalls = [
        {
            "lesson": entry["lesson"],
            "requested": entry["requested"],
            "ready": entry["ready"],
        }
        for entry in per_lesson
        if entry["ready"] < entry["requested"]
    ]

    return {
        "generated_at": _timestamp(),
        "book": _book_summary(document),
        "job": _job_summary(job),
        "lessons": len(job.lessons),
        "requested_items": job.total_requested,
        "ready_items": len(exported),
        "per_lesson": per_lesson,
        "shortfalls": shortfalls,
        "complete": not shortfalls,
        "statuses": {
            str(status): count
            for status, count in sorted(
                Counter(item.status for item in items).items()
            )
        },
        "exact_quote_checks": _exact_quote_checks(items),
        "verification_checks": _verification_checks(items),
        "chapter_checks": _chapter_checks(exported, job=job, document=document),
        "duplicate_count": _duplicate_count(exported, job=job),
        "audit": _audit_counts(items, job=job),
        # Ingestion is in the audit because most surprising results are
        # explained there: a chapter count that is one too high, or thousands of
        # hyphen repairs, says the excerpts were cut from a misread book.
        "ingestion": asdict(document.stats),
        "detection": {
            "style": document.detection_style,
            "confidence": document.detection_confidence,
            "warnings": list(document.detection_warnings),
        },
        "run": _plain(dict(run or {})),
    }


def _exact_quote_checks(items: list[VocabularyItem]) -> dict:
    """How many quotations were proved to be the book's own words.

    An item that never reached verification is not a failed check — it was
    dropped earlier, for being too easy or off the audience — so it is counted
    separately. A `READY` item with no record, on the other hand, is counted as
    a failure: a proved row is supposed to carry its proof.
    """
    passed = failed = 0
    for item in items:
        if not item.verification and item.status is not Status.READY:
            continue
        proved = item.verification.get("slice_matches") and item.verification.get(
            "present_in_chapter"
        )
        if proved:
            passed += 1
        else:
            failed += 1
    return {"passed": passed, "failed": failed}


def _verification_checks(items: list[VocabularyItem]) -> dict:
    """Every recorded check by name, so a pattern of failure is visible.

    Which check failed matters: `word_in_excerpt` failing repeatedly means the
    excerpt chooser is picking the wrong sentence, while `slice_matches`
    failing at all means an offset was corrupted, which is a different and much
    worse problem.
    """
    tally: dict[str, dict[str, int]] = {}
    for item in items:
        for name, passed in item.verification.items():
            counts = tally.setdefault(name, {"passed": 0, "failed": 0})
            counts["passed" if passed else "failed"] += 1
    return tally


def _chapter_checks(
    exported: list[VocabularyItem], *, job: JobConfig, document: BookDocument
) -> dict:
    """Whether each exported word was taught from its own lesson's chapters.

    Recomputed here rather than read back from the item, because this is the
    claim the workbook makes on the page — "Chapter 14", printed under a word
    in Lesson 2 — and it is cheap enough to prove again at the moment of
    writing the artifact.
    """
    passed = failed = 0
    for item in exported:
        locator = item.locator
        try:
            lesson = job.lesson(item.lesson)
        except KeyError:
            failed += 1
            continue
        in_range = (
            locator is not None
            and document.has_chapter(locator.chapter)
            and locator.chapter in lesson.chapters
        )
        if in_range:
            passed += 1
        else:
            failed += 1
    return {"passed": passed, "failed": failed}


def _duplicate_count(exported: list[VocabularyItem], *, job: JobConfig) -> int:
    """How many exported rows repeat a word already exported.

    Through the same registry the run was held to, so the number answers the
    question the operator configured rather than a similar one. It used to
    compare `item.lemma or item.normalized_term`, and `item.lemma` is never
    set — so a run configured for lemma-level uniqueness had its artifact
    report exact-match duplicates and call it a lemma check.

    Zero is the only acceptable value; it is reported rather than enforced
    because the item carrying the duplicate has been through every other check,
    and an operator deciding what to do about it needs to see the run.
    """
    return len(
        conflicts_among(
            [(item.term, item.lesson) for item in exported], job.dedupe
        )
    )


def _audit_counts(items: list[VocabularyItem], *, job: JobConfig) -> dict:
    """What the independent auditor concluded, and how independent it was.

    `independent` is part of the count because a pass from the model that wrote
    the item is worth less than a pass from another model, and a reader of this
    file six months later has no other way to know which one it was.
    """
    passed = sum(1 for item in items if item.audit and item.audit.passed)
    failed = sum(1 for item in items if item.audit and not item.audit.passed)
    unaudited = sum(
        1 for item in items if item.audit is None and item.status is Status.READY
    )
    ready = [item for item in items if item.status is Status.READY]
    pairings = Counter(
        (
            independence_of(item).generator,
            independence_of(item).auditor,
        )
        for item in ready
    )
    return {
        "passed": passed,
        "failed": failed,
        "ready_without_audit": unaudited,
        # What the job asked for, and what the endpoints did. They differ
        # whenever both chains fell back to the same provider, which is exactly
        # the case a configured-only answer would misreport.
        "independence_configured": job.llm.configured_independence,
        "independence_actual": weakest_independence(ready),
        "independence_required": job.llm.audit.requirement,
        "configured_generator": job.llm.generator.label,
        "configured_auditor": job.llm.auditor.label,
        "actual_pairings": [
            {"generator": generator, "auditor": auditor, "items": count}
            for (generator, auditor), count in sorted(pairings.items())
        ],
    }


def _book_summary(document: BookDocument) -> dict:
    """Which book this was, in terms that identify the exact file."""
    return {
        "title": document.title,
        "source_name": document.source_name,
        # The hash is what makes an artifact re-checkable: the same run against
        # a re-exported PDF is a different book, and the offsets in every
        # locator here belong to this one.
        "content_hash": document.content_hash,
        "page_count": document.page_count,
        "chapters": len(document.chapters),
        "chapter_numbers": document.chapter_numbers,
    }


def _job_summary(job: JobConfig) -> dict:
    """The settings that produced this run.

    Models are named; endpoints and the names of key variables are not. These
    files get attached to messages, and a model identifier explains a result
    while an endpoint only invites someone to try it.
    """
    return {
        "source": str(job.source_path) if job.source_path else None,
        "book_path": str(job.book.path),
        "audience": job.audience.label,
        "audience_description": job.audience.description,
        "vocabulary_per_lesson": job.vocabulary_per_lesson,
        "candidates_per_lesson": job.candidates_per_lesson,
        "dedupe": {"policy": job.dedupe.policy, "scope": job.dedupe.scope},
        "excerpt": {
            "max_characters": job.excerpt.max_characters,
            "min_characters": job.excerpt.min_characters,
            "max_sentences": job.excerpt.max_sentences,
            "prefer_unrepaired": job.excerpt.prefer_unrepaired,
            "unconfirmed_repairs": job.excerpt.unconfirmed_repairs,
        },
        "exclusions": {
            "terms": list(job.exclusions.terms),
            "allow_invented_terms": job.exclusions.allow_invented_terms,
        },
        "models": {
            "generator": job.llm.generator.label,
            "auditor": job.llm.auditor.label,
            "fallbacks": [provider.label for provider in job.llm.fallbacks],
            "audit_requirement": job.llm.audit.requirement,
            "audit_on_shared": job.llm.audit.on_shared,
            "configured_independence": job.llm.configured_independence,
            "max_attempts": job.llm.max_attempts,
            "cache": job.llm.cache,
        },
        "lessons": [
            {
                "lesson": lesson.lesson,
                "title": lesson.title,
                "reading_range": lesson.reading_range,
                "start_chapter": lesson.start_chapter,
                "end_chapter": lesson.end_chapter,
            }
            for lesson in sorted(job.lessons, key=lambda entry: entry.lesson)
        ],
    }


def _stable_order(items: list[VocabularyItem]) -> list[VocabularyItem]:
    """Every item in a fixed order, so two runs of a job can be diffed."""
    return sorted(
        items,
        key=lambda item: (
            item.lesson,
            item.order is None,
            item.order or 0,
            item.normalized_term,
            str(item.status),
        ),
    )


def _plain(value: object) -> object:
    """Coerce caller-supplied metadata into something `json.dumps` accepts.

    The run dictionary is assembled from timers, paths and provider objects by
    whoever is driving the pipeline. A run that did all its work should not lose
    its record on the last line because one value was a `Path`, so anything
    unrecognised becomes its string form instead of an exception.
    """
    if isinstance(value, str | int | float | bool | type(None)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if isinstance(value, list | tuple | set | frozenset):
        return [_plain(item) for item in value]
    return str(value)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _write_json(path: Path, payload: dict) -> Path:
    """Write one artifact as UTF-8 JSON that a person can read.

    `ensure_ascii=False` keeps Korean meanings and the book's punctuation as
    themselves rather than as escapes, and `newline="\\n"` stops Windows from
    rewriting the line endings of a file that is meant to be diffed.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path
