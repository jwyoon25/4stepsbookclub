"""What a vocabulary item is at each stage of its life, and what may change it.

The status model is not paperwork. `READY` is the only status the exporter
writes out, and the only way to reach it is `mark_ready`, which refuses without
a passed verification in hand. So "a hallucinated quotation cannot reach a Ready
row" is enforced by a signature rather than by a review step: there is no code
path that sets `READY` and does not hold proof.

The rest of the transitions are guarded for a duller reason. An item that fails
its audit and is quietly rewritten back to `GENERATED` would lose the record of
having failed, and the audit artifact would then describe a run that did not
happen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from ..errors import VerificationError
from ..source.excerpt import ExcerptLocator, ExcerptVerification


class Status(StrEnum):
    """Where an item has got to."""

    CANDIDATE = "CANDIDATE"
    SOURCE_VERIFIED = "SOURCE_VERIFIED"
    GENERATED = "GENERATED"
    AUDIT_PENDING = "AUDIT_PENDING"
    AUDIT_FAILED = "AUDIT_FAILED"
    READY = "READY"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


# Every item can fail or be sent for review from anywhere; nothing else is a
# shortcut. In particular there is no edge into READY, because `mark_ready` is
# the only way in and it checks more than the previous status.
ALLOWED_TRANSITIONS: dict[Status, set[Status]] = {
    Status.CANDIDATE: {Status.SOURCE_VERIFIED, Status.FAILED, Status.NEEDS_REVIEW},
    Status.SOURCE_VERIFIED: {Status.GENERATED, Status.FAILED, Status.NEEDS_REVIEW},
    Status.GENERATED: {Status.AUDIT_PENDING, Status.FAILED, Status.NEEDS_REVIEW},
    Status.AUDIT_PENDING: {
        Status.AUDIT_FAILED,
        Status.READY,
        Status.FAILED,
        Status.NEEDS_REVIEW,
    },
    Status.AUDIT_FAILED: {Status.FAILED, Status.NEEDS_REVIEW},
    Status.READY: {Status.NEEDS_REVIEW, Status.FAILED},
    Status.NEEDS_REVIEW: set(),
    Status.FAILED: set(),
}

# The status written into the workbook's own Status column. The Sheet treats
# that column as a note to the people working on the book rather than an input,
# so it carries the engine's word for "this row was proved", spelled the way a
# tutor reads it.
WORKBOOK_STATUS = "Ready"


@dataclass(frozen=True, slots=True)
class StatusChange:
    """One transition, with the reason it happened."""

    at: str
    was: Status
    became: Status
    reason: str


@dataclass(frozen=True, slots=True)
class RubricScore:
    """A model's structured judgement of one candidate word."""

    difficulty: int
    general_utility: int
    context_quality: int
    educational_value: int
    generality: int
    exclusion_risk: int
    note: str | None = None

    @property
    def total(self) -> float:
        """One number for ranking, with exclusion risk counted against.

        The weights are deliberately flat except for exclusion risk. Ranking is
        there to order a pool that has already been filtered, not to be a model
        of pedagogy, and a rubric with invented precision would read as more
        authoritative than it is.
        """
        return (
            self.difficulty
            + self.general_utility
            + self.context_quality
            + self.educational_value
            + self.generality
            - 2 * self.exclusion_risk
        )


# What each of the auditor's assessments has to say for an item to pass. A
# value not listed here is a complaint, and one complaint is enough.
#
# This table, not the auditor's own `verdict` field, is what decides whether an
# item passed. A free endpoint returning `{"verdict": "PASS", "korean_accuracy":
# "INACCURATE"}` is not a rare event and it is not a judgement worth honouring;
# it is a model that filled in a summary field without reading back what it had
# just written. `prompts/audit.md` asks for consistency, and consistency is
# checked here rather than assumed, because a prompt is a request and this is a
# rule.
#
# `MINOR_ISSUE` is not acceptable either. It reads like a small thing, and for
# an internal draft it would be; for a definition a student learns from, "the
# Korean is nearly right" is not a state anything should ship in. An item can
# always be replaced from the pool, so the cost of being strict here is a
# candidate, and the cost of being lax is a wrong workbook row.
AUDIT_REQUIRED_ASSESSMENTS: dict[str, frozenset[str]] = {
    "difficulty": frozenset({"APPROPRIATE"}),
    "definition_accuracy": frozenset({"ACCURATE"}),
    "korean_accuracy": frozenset({"ACCURATE"}),
    "context_accuracy": frozenset({"ACCURATE"}),
    "excerpt_fit": frozenset({"GOOD"}),
}

# How each assessment is named in a sentence an operator reads.
AUDIT_ASSESSMENT_LABELS: dict[str, str] = {
    "difficulty": "the difficulty",
    "definition_accuracy": "the definition",
    "korean_accuracy": "the Korean meaning",
    "context_accuracy": "the context sentence",
    "excerpt_fit": "the excerpt",
}


@dataclass(frozen=True, slots=True)
class AuditVerdict:
    """What the independent auditor concluded about one finished item."""

    verdict: str
    difficulty: str
    definition_accuracy: str
    korean_accuracy: str
    context_accuracy: str
    excerpt_fit: str
    notes: str | None = None
    provider: str | None = None
    model: str | None = None

    @property
    def complaints(self) -> list[str]:
        """Every assessment that is not one this engine accepts."""
        return [
            name
            for name, acceptable in AUDIT_REQUIRED_ASSESSMENTS.items()
            if str(getattr(self, name, "")).strip().upper() not in acceptable
        ]

    @property
    def passed(self) -> bool:
        """Whether this verdict clears an item, decided field by field.

        Every condition has to hold: the top-level verdict *and* all five
        assessments. A model cannot pass an item by writing `PASS` over its own
        findings, and it cannot fail one by accident either — a `FAIL` with
        five clean assessments still fails, because the auditor saw something
        it did not have a field for and said so in the only way it could.
        """
        return self.verdict.strip().upper() == "PASS" and not self.complaints


@dataclass(slots=True)
class Provenance:
    """Where every part of an item came from.

    Kept per item rather than per run because the question an operator asks is
    always about one row: where did this quotation come from, and which model
    wrote this definition.
    """

    source_name: str = ""
    content_hash: str = ""
    sentence_ids: tuple[str, ...] = ()
    pages: tuple[int, ...] = ()
    occurrence_count: int = 0
    occurrence_index: int | None = None
    generator_provider: str | None = None
    generator_model: str | None = None
    auditor_provider: str | None = None
    auditor_model: str | None = None

    def as_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "content_hash": self.content_hash,
            "sentence_ids": list(self.sentence_ids),
            "pages": list(self.pages),
            "occurrence_count": self.occurrence_count,
            "occurrence_index": self.occurrence_index,
            "generator_provider": self.generator_provider,
            "generator_model": self.generator_model,
            "auditor_provider": self.auditor_provider,
            "auditor_model": self.auditor_model,
        }


@dataclass(slots=True)
class VocabularyItem:
    """One workbook row, at whatever stage it has reached."""

    lesson: int
    term: str
    normalized_term: str
    lemma: str = ""
    status: Status = Status.CANDIDATE
    order: int | None = None

    locator: ExcerptLocator | None = None
    excerpt: str | None = None
    definition: str | None = None
    korean_meaning: str | None = None
    excerpt_context: str | None = None

    score: RubricScore | None = None
    audit: AuditVerdict | None = None
    provenance: Provenance = field(default_factory=Provenance)
    history: list[StatusChange] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    verification: dict[str, bool] = field(default_factory=dict)
    replaced: str | None = None

    @property
    def chapter_reference(self) -> str | None:
        """The chapter citation, derived from the locator and nowhere else."""
        return self.locator.chapter_reference if self.locator else None

    @property
    def is_ready(self) -> bool:
        return self.status is Status.READY

    def transition(self, status: Status, reason: str) -> None:
        """Move to a new status, refusing moves the lifecycle does not have."""
        if status is Status.READY:
            raise VerificationError(
                "READY is reached through mark_ready(), which requires a passed "
                "verification. It cannot be assigned directly."
            )
        if status not in ALLOWED_TRANSITIONS[self.status]:
            raise VerificationError(
                f"{self.term!r} cannot move from {self.status} to {status}."
            )
        self._record(status, reason)

    def mark_ready(self, verification: ExcerptVerification, reason: str) -> None:
        """Promote a fully proved item, and refuse anything less.

        The three conditions are the ones that cannot be recovered from later:
        the item must hold a locator, that locator must have verified against
        the book, and the audit must have passed. An item missing any of them is
        a bug in the caller, so this raises rather than returning False.
        """
        if self.status is not Status.AUDIT_PENDING:
            raise VerificationError(
                f"{self.term!r} is {self.status}; only an audited item can be "
                "marked ready."
            )
        if not verification.ok:
            raise VerificationError(
                f"{self.term!r} cannot be marked ready: "
                f"{', '.join(verification.failed()) or 'verification failed'}."
            )
        if self.locator is None or not self.excerpt:
            raise VerificationError(
                f"{self.term!r} cannot be marked ready without a source excerpt."
            )
        if self.audit is None or not self.audit.passed:
            raise VerificationError(
                f"{self.term!r} cannot be marked ready without a passed audit."
            )

        self.verification = dict(verification.checks)
        self._record(Status.READY, reason)

    def fail(self, reason: str) -> None:
        """Take an item out of the running, keeping why."""
        self.failures.append(reason)
        if self.status in {Status.FAILED, Status.NEEDS_REVIEW}:
            return
        self._record(Status.FAILED, reason)

    def needs_review(self, reason: str) -> None:
        """Park an item for a human, keeping why."""
        self.failures.append(reason)
        if self.status is Status.NEEDS_REVIEW:
            return
        self._record(Status.NEEDS_REVIEW, reason)

    def _record(self, status: Status, reason: str) -> None:
        self.history.append(
            StatusChange(
                at=datetime.now(UTC).isoformat(timespec="seconds"),
                was=self.status,
                became=status,
                reason=reason,
            )
        )
        self.status = status

    def as_dict(self) -> dict:
        return {
            "lesson": self.lesson,
            "order": self.order,
            "term": self.term,
            "normalized_term": self.normalized_term,
            "lemma": self.lemma,
            "status": str(self.status),
            "korean_meaning": self.korean_meaning,
            "definition": self.definition,
            "excerpt": self.excerpt,
            "excerpt_context": self.excerpt_context,
            "chapter_reference": self.chapter_reference,
            "locator": self.locator.as_dict() if self.locator else None,
            "score": (
                {
                    "difficulty": self.score.difficulty,
                    "general_utility": self.score.general_utility,
                    "context_quality": self.score.context_quality,
                    "educational_value": self.score.educational_value,
                    "generality": self.score.generality,
                    "exclusion_risk": self.score.exclusion_risk,
                    "total": self.score.total,
                    "note": self.score.note,
                }
                if self.score
                else None
            ),
            "audit": (
                {
                    "verdict": self.audit.verdict,
                    "difficulty": self.audit.difficulty,
                    "definition_accuracy": self.audit.definition_accuracy,
                    "korean_accuracy": self.audit.korean_accuracy,
                    "context_accuracy": self.audit.context_accuracy,
                    "excerpt_fit": self.audit.excerpt_fit,
                    "notes": self.audit.notes,
                    "provider": self.audit.provider,
                    "model": self.audit.model,
                }
                if self.audit
                else None
            ),
            "verification": self.verification,
            "provenance": self.provenance.as_dict(),
            "failures": self.failures,
            "replaced": self.replaced,
            "history": [
                {
                    "at": change.at,
                    "was": str(change.was),
                    "became": str(change.became),
                    "reason": change.reason,
                }
                for change in self.history
            ],
        }
