"""The audit stage: what a verdict has to say before an item is allowed through.

Every test here is about the same question asked from a different angle — can a
model get an item past this stage by saying the right word in the wrong field.
The answer has to be no whatever the model writes, because the audit is the only
stage that judges meaning, and a stage that can be talked into a PASS is not a
check.
"""

from __future__ import annotations

import pytest

from bookengine.vocabulary.audit import apply_verdicts
from bookengine.vocabulary.models import AuditVerdict, Status, VocabularyItem
from bookengine.vocabulary.schemas import AuditItemVerdict

CLEAN = {
    "verdict": "PASS",
    "difficulty": "APPROPRIATE",
    "definition_accuracy": "ACCURATE",
    "korean_accuracy": "ACCURATE",
    "context_accuracy": "ACCURATE",
    "excerpt_fit": "GOOD",
}


def verdict(**overrides) -> AuditVerdict:
    return AuditVerdict(**{**CLEAN, **overrides})


# --- the deterministic pass/fail decision ----------------------------------


def test_a_clean_verdict_passes():
    assert verdict().passed
    assert verdict().complaints == []


@pytest.mark.parametrize(
    "field, value",
    [
        ("korean_accuracy", "INACCURATE"),
        ("korean_accuracy", "MINOR_ISSUE"),
        ("context_accuracy", "INACCURATE"),
        ("context_accuracy", "MINOR_ISSUE"),
        ("definition_accuracy", "INACCURATE"),
        ("definition_accuracy", "MINOR_ISSUE"),
        ("difficulty", "TOO_HARD"),
        ("difficulty", "TOO_EASY"),
        ("excerpt_fit", "POOR"),
        ("excerpt_fit", "WEAK"),
    ],
)
def test_one_bad_assessment_fails_the_item_however_the_verdict_reads(field, value):
    """A PASS written over a finding is not a pass.

    This is the shape a free endpoint actually returns: five fields judged
    honestly and a summary field filled in from habit.
    """
    rejected = verdict(**{field: value})
    assert not rejected.passed
    assert rejected.complaints == [field]


def test_a_failing_verdict_fails_even_with_five_clean_assessments():
    """The auditor saw something it had no field for. Believe it."""
    assert not verdict(verdict="FAIL").passed


def test_a_verdict_is_read_case_and_space_insensitively():
    """Free endpoints are inconsistent about casing, and that is not a finding."""
    assert verdict(verdict=" pass ", korean_accuracy="accurate").passed


def test_every_assessment_is_named_when_several_are_wrong():
    rejected = verdict(korean_accuracy="INACCURATE", excerpt_fit="POOR")
    assert set(rejected.complaints) == {"korean_accuracy", "excerpt_fit"}


# --- the same rule, applied at the boundary where the answer arrives -------


def test_the_schema_rewrites_a_verdict_that_contradicts_its_own_findings():
    """The findings are specific claims; the verdict is a summary of them."""
    parsed = AuditItemVerdict(
        word="reluctant", **{**CLEAN, "korean_accuracy": "INACCURATE"}
    )
    assert parsed.verdict == "FAIL"


def test_the_schema_leaves_a_consistent_verdict_alone():
    assert AuditItemVerdict(word="reluctant", **CLEAN).verdict == "PASS"


def test_one_inconsistent_verdict_does_not_cost_the_batch_its_others():
    """Raising would throw away every correct verdict beside the bad one."""
    good = AuditItemVerdict(word="reluctant", **CLEAN)
    bad = AuditItemVerdict(
        word="monotonous", **{**CLEAN, "context_accuracy": "INACCURATE"}
    )
    assert (good.verdict, bad.verdict) == ("PASS", "FAIL")


# --- what that means for an item ------------------------------------------


def audited_item(term: str) -> VocabularyItem:
    item = VocabularyItem(lesson=1, term=term, normalized_term=term)
    item.transition(Status.SOURCE_VERIFIED, "test")
    item.transition(Status.GENERATED, "test")
    item.transition(Status.AUDIT_PENDING, "test")
    return item


def test_an_item_whose_korean_was_faulted_is_failed_and_says_why():
    item = audited_item("reluctant")
    passed, failed = apply_verdicts(
        [item], {"reluctant": verdict(korean_accuracy="INACCURATE")}
    )

    assert (passed, failed) == ([], [item])
    assert item.status is Status.FAILED
    assert "the Korean meaning (INACCURATE)" in item.failures[0]


def test_a_failure_message_names_only_what_was_actually_wrong():
    item = audited_item("monotonous")
    apply_verdicts([item], {"monotonous": verdict(excerpt_fit="WEAK")})

    assert "the excerpt (WEAK)" in item.failures[0]
    assert "Korean" not in item.failures[0]


def test_an_item_with_no_verdict_is_not_a_pass():
    """A truncated reply from a rate-limited endpoint must not read as approval."""
    item = audited_item("predicament")
    passed, failed = apply_verdicts([item], {})

    assert (passed, failed) == ([], [item])
    assert item.status is Status.FAILED
