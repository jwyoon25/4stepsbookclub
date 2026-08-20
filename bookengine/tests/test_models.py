"""The status lifecycle, which is where the central guarantee is enforced."""

from __future__ import annotations

import pytest

from bookengine.errors import VerificationError
from bookengine.source.excerpt import ExcerptLocator, ExcerptVerification
from bookengine.vocabulary.models import AuditVerdict, Status, VocabularyItem


def fresh() -> VocabularyItem:
    return VocabularyItem(lesson=1, term="lurch", normalized_term="lurch")


def audited() -> VocabularyItem:
    item = fresh()
    item.locator = ExcerptLocator(chapter=2, char_start=0, char_end=10)
    item.excerpt = "a sickening lurch"
    item.audit = AuditVerdict(
        verdict="PASS",
        difficulty="APPROPRIATE",
        definition_accuracy="ACCURATE",
        korean_accuracy="ACCURATE",
        context_accuracy="ACCURATE",
        excerpt_fit="GOOD",
    )
    item.transition(Status.SOURCE_VERIFIED, "t")
    item.transition(Status.GENERATED, "t")
    item.transition(Status.AUDIT_PENDING, "t")
    return item


def test_ready_cannot_be_assigned_directly():
    with pytest.raises(VerificationError, match="mark_ready"):
        fresh().transition(Status.READY, "please")


def test_stages_cannot_be_skipped():
    with pytest.raises(VerificationError, match="cannot move"):
        fresh().transition(Status.GENERATED, "skip the source check")


def test_ready_needs_a_passed_verification():
    item = audited()
    with pytest.raises(VerificationError):
        item.mark_ready(
            ExcerptVerification(ok=False, checks={"slice_matches": False}), "x"
        )
    assert item.status is Status.AUDIT_PENDING


def test_ready_needs_a_source_excerpt():
    item = audited()
    item.excerpt = None
    with pytest.raises(VerificationError, match="source excerpt"):
        item.mark_ready(ExcerptVerification(ok=True), "x")


def test_ready_needs_a_passed_audit():
    item = audited()
    item.audit = None
    with pytest.raises(VerificationError, match="audit"):
        item.mark_ready(ExcerptVerification(ok=True), "x")


def test_a_failed_audit_verdict_blocks_ready():
    item = audited()
    item.audit = AuditVerdict(
        verdict="FAIL",
        difficulty="TOO_HARD",
        definition_accuracy="INACCURATE",
        korean_accuracy="ACCURATE",
        context_accuracy="ACCURATE",
        excerpt_fit="GOOD",
    )
    with pytest.raises(VerificationError, match="audit"):
        item.mark_ready(ExcerptVerification(ok=True), "x")


def test_a_fully_proved_item_becomes_ready_and_keeps_its_checks():
    item = audited()
    item.mark_ready(
        ExcerptVerification(ok=True, checks={"slice_matches": True}), "proved"
    )
    assert item.status is Status.READY
    assert item.verification == {"slice_matches": True}
    assert item.history[-1].became is Status.READY


def test_the_chapter_reference_is_derived_and_not_stored():
    item = fresh()
    assert item.chapter_reference is None
    item.locator = ExcerptLocator(chapter=17, char_start=0, char_end=5)
    assert item.chapter_reference == "Chapter 17"


def test_failing_keeps_the_reason_and_does_not_move_a_dead_item():
    item = fresh()
    item.fail("no usable passage")
    item.fail("also this")
    assert item.status is Status.FAILED
    assert item.failures == ["no usable passage", "also this"]
    assert len([c for c in item.history if c.became is Status.FAILED]) == 1
