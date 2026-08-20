"""The checks that stand between a generated item and a workbook row.

Everything in this module is deterministic. Nothing here asks a model anything,
and nothing here is persuadable. That is the point: the pipeline above is a
negotiation with a language model, and this is the part that is not.

The checks are run twice by design. Once when an item is first assembled, and
again over the finished set after audit replacements have happened, because a
replacement changes the duplicate picture and the per-lesson counts for every
other item in the lesson. A run that verified only the first time would be
verifying a set that no longer exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import JobConfig
from ..export.workbook_contract import VOCABULARY_FIELD_LIMITS
from ..source.document import BookDocument
from ..source.excerpt import (
    ExcerptVerification,
    unconfirmed_words,
    verify_excerpt,
)
from ..source.search import occurs_in_chapters
from ..source.text import normalize_term
from .models import Status, VocabularyItem

# The workbook schema's field name for each part of an item, so a length
# complaint names the field the tutor would see rather than a Python attribute.
_FIELD_SOURCES: tuple[tuple[str, str], ...] = (
    ("term", "term"),
    ("koreanMeaning", "korean_meaning"),
    ("definition", "definition"),
    ("bookExcerpt", "excerpt"),
    ("excerptContext", "excerpt_context"),
)


@dataclass(slots=True)
class LessonOutcome:
    """How one lesson finished."""

    lesson: int
    requested: int
    ready: int
    failed: int
    needs_review: int
    shortfall_reasons: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.ready == self.requested


@dataclass(slots=True)
class FinalReport:
    """The verdict on a whole run."""

    lessons: list[LessonOutcome] = field(default_factory=list)
    duplicate_conflicts: list[str] = field(default_factory=list)
    item_failures: list[str] = field(default_factory=list)
    quote_checks_passed: int = 0
    quote_checks_failed: int = 0
    chapter_checks_passed: int = 0
    chapter_checks_failed: int = 0
    audit_passed: int = 0
    audit_failed: int = 0

    @property
    def ok(self) -> bool:
        return (
            all(lesson.complete for lesson in self.lessons)
            and not self.duplicate_conflicts
            and not self.item_failures
        )

    @property
    def ready_total(self) -> int:
        return sum(lesson.ready for lesson in self.lessons)

    @property
    def requested_total(self) -> int:
        return sum(lesson.requested for lesson in self.lessons)

    def render(self) -> str:
        """The failure message an operator can act on.

        "Generation failed" is not an actionable sentence. Which lesson, how
        many it reached, and why the missing ones were rejected, is.
        """
        lines: list[str] = []
        for lesson in self.lessons:
            if lesson.complete:
                continue
            lines.append(
                f"Lesson {lesson.lesson} could not reach {lesson.requested} "
                f"verified vocabulary items."
            )
            lines.append(f"  {lesson.ready} items are READY.")
            if lesson.failed:
                lines.append(f"  {lesson.failed} candidates were rejected.")
            if lesson.needs_review:
                lines.append(f"  {lesson.needs_review} items need human review.")
            for reason in lesson.shortfall_reasons[:6]:
                lines.append(f"    - {reason}")
            remaining = len(lesson.shortfall_reasons) - 6
            if remaining > 0:
                lines.append(f"    - and {remaining} further reasons; see audit.json")

        for conflict in self.duplicate_conflicts:
            lines.append(f"Duplicate vocabulary: {conflict}")
        for failure in self.item_failures:
            lines.append(f"Final verification rejected an item: {failure}")

        if not lines:
            return "Final verification passed."
        lines.append("Generation was not marked successful. See audit.json.")
        return "\n".join(lines)


def verify_item(
    document: BookDocument, job: JobConfig, item: VocabularyItem
) -> ExcerptVerification:
    """Run every objective check one item has to survive.

    The excerpt checks come from `source.excerpt`, which knows nothing about
    vocabulary; the rest are the lesson-shaped ones. They are collected into a
    single verification object because `VocabularyItem.mark_ready` will not
    promote an item without one, and there should be exactly one thing to hold.
    """
    if item.locator is None or not item.excerpt:
        verification = ExcerptVerification(ok=False)
        verification.checks["has_source_excerpt"] = False
        verification.reasons.append(
            f"{item.term!r} has no source excerpt, so nothing about it can be proved."
        )
        return verification

    verification = verify_excerpt(document, item.locator, item.excerpt, term=item.term)
    verification.checks["has_source_excerpt"] = True

    try:
        lesson = job.lesson(item.lesson)
    except KeyError:
        verification.checks["lesson_exists"] = False
        verification.reasons.append(
            f"{item.term!r} is assigned to lesson {item.lesson}, which the job "
            "does not define."
        )
        verification.ok = False
        return verification

    verification.checks["lesson_exists"] = True

    chapters = lesson.chapters
    verification.checks["chapter_in_lesson_range"] = item.locator.chapter in chapters
    if not verification.checks["chapter_in_lesson_range"]:
        verification.reasons.append(
            f"{item.term!r} is quoted from chapter {item.locator.chapter}, which "
            f"is outside lesson {lesson.lesson} ({lesson.reading_range})."
        )

    verification.checks["word_occurs_in_lesson_range"] = occurs_in_chapters(
        document, item.term, chapters
    )
    if not verification.checks["word_occurs_in_lesson_range"]:
        verification.reasons.append(
            f"{item.term!r} does not occur in {lesson.reading_range}, so a "
            f"student reading lesson {lesson.lesson} would never meet it."
        )

    # The chapter reference is derived from the locator, so this can only fail
    # if something reintroduced a claimed chapter number. It is checked anyway,
    # because that is precisely the regression worth catching.
    verification.checks["chapter_reference_is_derived"] = (
        item.chapter_reference == f"Chapter {item.locator.chapter}"
    )
    if not verification.checks["chapter_reference_is_derived"]:
        verification.reasons.append(
            f"{item.term!r} carries the chapter reference {item.chapter_reference!r}, "
            f"which is not derived from its source locator."
        )

    for label, attribute in (
        ("definition_present", "definition"),
        ("korean_meaning_present", "korean_meaning"),
        ("excerpt_context_present", "excerpt_context"),
    ):
        value = getattr(item, attribute)
        verification.checks[label] = bool(value and value.strip())
        if not verification.checks[label]:
            verification.reasons.append(
                f"{item.term!r} has no {attribute.replace('_', ' ')}."
            )

    unconfirmed = unconfirmed_words(document, item.locator)
    verification.checks["excerpt_is_confirmed_text"] = (
        job.excerpt.allow_uncertain_repairs or not unconfirmed
    )
    if not verification.checks["excerpt_is_confirmed_text"]:
        listed = ", ".join(repr(word) for word in unconfirmed[:3])
        verification.reasons.append(
            f"{item.term!r}: the excerpt reads {listed}, rejoined across a line "
            "break in a form the book itself does not use elsewhere. Those are "
            "this engine's characters, not the book's."
        )

    verification.checks["audit_passed"] = (
        item.audit is not None and item.audit.passed
    )
    if not verification.checks["audit_passed"]:
        verification.reasons.append(
            f"{item.term!r} has not passed an independent audit."
        )

    verification.checks["within_workbook_limits"] = True
    for schema_field, attribute in _FIELD_SOURCES:
        limit = VOCABULARY_FIELD_LIMITS.get(schema_field)
        value = getattr(item, attribute) or ""
        if limit is not None and len(value) > limit:
            verification.checks["within_workbook_limits"] = False
            verification.reasons.append(
                f"{item.term!r}: {schema_field} is {len(value)} characters, and "
                f"the workbook content schema allows {limit}."
            )

    verification.checks["excerpt_length_in_range"] = (
        job.excerpt.min_characters <= len(item.excerpt) <= job.excerpt.max_characters
    )
    if not verification.checks["excerpt_length_in_range"]:
        verification.reasons.append(
            f"{item.term!r}: the excerpt is {len(item.excerpt)} characters, and "
            f"the job allows {job.excerpt.min_characters}-"
            f"{job.excerpt.max_characters}."
        )

    verification.ok = all(verification.checks.values())
    return verification


def find_duplicates(items: list[VocabularyItem]) -> list[str]:
    """Exact normalized duplicates across everything being exported.

    The registry already prevents these while candidates are being selected.
    This is the independent second look, run over the finished set, because the
    guarantee is about what leaves the engine rather than about what the
    registry believed at the time.
    """
    seen: dict[str, VocabularyItem] = {}
    conflicts: list[str] = []

    for item in items:
        key = normalize_term(item.term)
        if key in seen:
            first = seen[key]
            conflicts.append(
                f"{item.term!r} appears in lesson {first.lesson} (order "
                f"{first.order}) and lesson {item.lesson} (order {item.order})."
            )
            continue
        seen[key] = item

    return conflicts


def final_verification(
    document: BookDocument, job: JobConfig, items: list[VocabularyItem]
) -> FinalReport:
    """Re-prove the whole finished set, after every replacement has settled.

    An item that fails here is demoted rather than quietly dropped: a run that
    exported nineteen rows and called itself successful is the exact failure the
    per-lesson count check exists to prevent.
    """
    report = FinalReport()

    for item in list(items):
        if item.status is not Status.READY:
            continue
        verification = verify_item(document, job, item)

        quote_ok = all(
            verification.checks.get(name, False)
            for name in ("slice_matches", "present_in_chapter", "word_in_excerpt")
        )
        report.quote_checks_passed += int(quote_ok)
        report.quote_checks_failed += int(not quote_ok)

        chapter_ok = verification.checks.get(
            "chapter_in_lesson_range", False
        ) and verification.checks.get("chapter_reference_is_derived", False)
        report.chapter_checks_passed += int(chapter_ok)
        report.chapter_checks_failed += int(not chapter_ok)

        if verification.checks.get("audit_passed", False):
            report.audit_passed += 1
        else:
            report.audit_failed += 1

        if not verification.ok:
            reason = verification.reasons[0] if verification.reasons else "unknown"
            report.item_failures.append(reason)
            item.needs_review(f"Final verification failed: {reason}")

    report.duplicate_conflicts = find_duplicates(
        [item for item in items if item.status is Status.READY]
    )
    for conflict in report.duplicate_conflicts:
        report.item_failures.append(conflict)

    for lesson in job.lessons:
        in_lesson = [item for item in items if item.lesson == lesson.lesson]
        ready = [item for item in in_lesson if item.status is Status.READY]
        report.lessons.append(
            LessonOutcome(
                lesson=lesson.lesson,
                requested=job.vocabulary_per_lesson,
                ready=len(ready),
                failed=sum(1 for item in in_lesson if item.status is Status.FAILED),
                needs_review=sum(
                    1 for item in in_lesson if item.status is Status.NEEDS_REVIEW
                ),
                shortfall_reasons=_shortfall_reasons(in_lesson),
            )
        )

    return report


def _shortfall_reasons(items: list[VocabularyItem]) -> list[str]:
    """Why a lesson came up short, grouped so the list stays readable."""
    counts: dict[str, int] = {}
    for item in items:
        if item.status in {Status.READY}:
            continue
        for failure in item.failures[:1]:
            counts[failure] = counts.get(failure, 0) + 1

    return [
        f"{count} candidate(s): {reason}" if count > 1 else reason
        for reason, count in sorted(counts.items(), key=lambda pair: -pair[1])
    ]


def assign_orders(items: list[VocabularyItem]) -> None:
    """Number the ready items within each lesson, from 1.

    Order is a workbook column and the array order is what the renderer uses for
    numbering, so it is assigned once, at the end, over the set that survived.
    """
    by_lesson: dict[int, int] = {}
    for item in sorted(items, key=lambda entry: (entry.lesson, entry.order or 0)):
        if item.status is not Status.READY:
            item.order = None
            continue
        by_lesson[item.lesson] = by_lesson.get(item.lesson, 0) + 1
        item.order = by_lesson[item.lesson]
