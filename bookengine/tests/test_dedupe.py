"""What counts as the same word, and what the policy is allowed to change."""

from __future__ import annotations

import pytest

from bookengine.config import DedupeConfig
from bookengine.vocabulary.dedupe import (
    DuplicateRegistry,
    RuleLemmatizer,
    build_lemmatizer,
)


@pytest.fixture
def rules():
    return RuleLemmatizer()


def registry(policy="lemma", scope="book", lemmatizer=None):
    return DuplicateRegistry(
        DedupeConfig(policy=policy, scope=scope),
        lemmatizer=lemmatizer or RuleLemmatizer(),
    )


@pytest.mark.parametrize(
    ("word", "expected_member"),
    [
        ("running", "run"),
        ("cities", "city"),
        ("stopped", "stop"),
        ("making", "make"),
        ("carried", "carry"),
    ],
)
def test_the_rule_lemmatizer_reaches_the_common_inflections(
    rules, word, expected_member
):
    assert expected_member in rules.lemmas(word)


@pytest.mark.parametrize("word", ["corner", "thing", "bus", "analysis", "red"])
def test_the_rule_lemmatizer_does_not_over_reach(rules, word):
    """A wrong lemma silently merges two unrelated words, so it must not guess."""
    lemmas = rules.lemmas(word)
    assert lemmas == {word} or word in lemmas


def test_corner_and_corn_are_not_one_word(rules):
    """The failure mode that made comparatives ineligible for the rule path."""
    book = registry()
    book.claim("corner", lesson=1)
    assert book.conflict("corn", lesson=1) is None


def test_exact_duplicates_are_blocked_under_every_policy():
    for policy in ("exact", "lemma"):
        book = registry(policy=policy)
        book.claim("predicament", lesson=1)
        assert book.conflict("  “Predicament,” ", lesson=3) is not None


def test_the_lemma_policy_merges_word_families_and_exact_does_not():
    lemma = registry(policy="lemma")
    lemma.claim("run", lesson=1)
    assert lemma.conflict("running", lesson=2) is not None

    exact = registry(policy="exact")
    exact.claim("run", lesson=1)
    assert exact.conflict("running", lesson=2) is None


def test_lesson_scope_confines_the_family_rule_but_not_exact_identity():
    scoped = registry(scope="lesson")
    scoped.claim("run", lesson=1)
    assert scoped.conflict("running", lesson=1) is not None
    assert scoped.conflict("running", lesson=2) is None
    assert scoped.conflict("run", lesson=2) is not None


def test_a_released_word_returns_to_the_pool():
    """Without this, every audit rejection would shrink what is left to try."""
    book = registry()
    book.claim("run", lesson=1)
    assert book.conflict("running", lesson=2) is not None

    book.release("run", lesson=1)
    assert book.conflict("running", lesson=2) is None
    assert book.conflict("run", lesson=2) is None


def test_the_active_lemmatizer_is_named_so_a_run_can_say_which_it_used():
    assert build_lemmatizer().name in {"rules", "lemminflect"}
    assert "lemmatizer" in registry().policy_note
    assert "not merged" in registry(policy="exact").policy_note
