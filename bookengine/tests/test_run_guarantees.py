"""Two promises the run makes about itself, checked independently of it.

The first is that no word is taught twice — under whatever definition of
"twice" the job configured, not under a weaker one that happens to be easier to
check at the end.

The second is that a lesson coming up short means the book ran out of usable
words, not that a counter ran out. A run that stopped early and reported "could
not reach 20 verified items" would send an operator looking for a problem in
the book that is not there.
"""

from __future__ import annotations

import pytest

from bookengine.config import DedupeConfig
from bookengine.llm.chain import ProviderChain
from bookengine.prompts import PromptLibrary
from bookengine.vocabulary.candidates import Candidate
from bookengine.vocabulary.dedupe import (
    DuplicateRegistry,
    RuleLemmatizer,
    build_lemmatizer,
    conflicts_among,
)
from bookengine.vocabulary.models import RubricScore, Status, VocabularyItem
from bookengine.vocabulary.pipeline import RunStats, build_lesson
from bookengine.vocabulary.verify import find_duplicates
from conftest import build_job
from fakes import ScriptedProvider


def ready(term: str, lesson: int, order: int) -> VocabularyItem:
    """An item as `find_duplicates` sees it: a word, a lesson, a place."""
    item = VocabularyItem(lesson=lesson, term=term, normalized_term=term.lower())
    item.order = order
    return item


# --- the duplicate promise -------------------------------------------------


def test_the_final_check_applies_the_lemma_policy_when_the_job_asks_for_it():
    """The regression: it used to compare normalized spellings and stop there.

    A run configured for lemma-level uniqueness would then have the registry
    block `running` during selection and the final check pass a set containing
    both — proving something the job never asked for.
    """
    items = [ready("run", 1, 1), ready("running", 2, 1)]

    assert find_duplicates(items, DedupeConfig(policy="lemma")) != []
    assert find_duplicates(items, DedupeConfig(policy="exact")) == []


def test_exact_duplicates_are_refused_under_every_policy():
    """Two rows with the same word on them is a defect whatever the policy."""
    items = [ready("reluctant", 1, 1), ready("Reluctant,", 3, 4)]

    for policy in ("exact", "lemma"):
        assert find_duplicates(items, DedupeConfig(policy=policy)) != []


def test_the_lesson_scope_narrows_the_family_check_but_not_the_exact_one():
    across = [ready("run", 1, 1), ready("running", 2, 1)]
    within = [ready("run", 1, 1), ready("running", 1, 2)]
    scoped = DedupeConfig(policy="lemma", scope="lesson")

    assert find_duplicates(across, scoped) == []
    assert find_duplicates(within, scoped) != []


def test_the_final_check_defaults_to_the_engine_s_policy_not_the_laxest_one():
    """A caller who forgets the policy must not get a weaker guarantee."""
    items = [ready("run", 1, 1), ready("running", 2, 1)]

    assert DedupeConfig().policy == "lemma"
    assert find_duplicates(items) != []


def test_selection_and_final_validation_use_one_mechanism():
    """Whatever the registry blocks, the final check must also find.

    Two implementations of "the same word" drift, and the one that drifts is
    the one nothing is testing.
    """
    lemmatizer = RuleLemmatizer()
    config = DedupeConfig(policy="lemma")
    registry = DuplicateRegistry(config, lemmatizer=lemmatizer)
    registry.claim("run", lesson=1)

    blocked = registry.conflict("running", lesson=2) is not None
    found = conflicts_among([("run", 1), ("running", 2)], config, lemmatizer) != []

    assert blocked == found is True


@pytest.mark.parametrize(
    "first, second",
    [("corner", "corn"), ("bus", "bu"), ("witness", "witnes")],
)
def test_the_conservative_lemmatizer_is_not_loosened_by_any_of_this(first, second):
    """`corner` must not reduce to `corn` and quietly drop a word from the book."""
    assert find_duplicates(
        [ready(first, 1, 1), ready(second, 2, 1)], DedupeConfig(policy="lemma")
    ) == []


# --- the exhaustion promise ------------------------------------------------


def pool(size: int) -> list[Candidate]:
    """A pool of real words from the fixture book's first six chapters."""
    words = [
        "predicament", "monotonous", "articulate", "deliberate", "collective",
        "exhaustion", "estimation", "negotiable", "settlement", "disinfectant",
        "rehearsed", "indifferent", "consider", "arranged", "scratched",
        "travelled", "surfaced", "carried", "counted", "wanted", "morning",
        "afternoon", "everyone", "somehow", "certain", "memory", "furniture",
        "beginning", "imagine", "ceiling",
    ]
    return [
        Candidate(
            term=word, sense="the usual sense", score=RubricScore(4, 4, 4, 4, 4, 1)
        )
        for word in words[:size]
    ]


def fill(document, job, provider, candidates, progress=None):
    from bookengine.vocabulary.pipeline import Progress

    generator = ProviderChain(providers=[provider])
    auditor = ProviderChain(providers=[provider.as_auditor()])
    stats = RunStats()
    produced = build_lesson(
        document,
        job,
        job.lesson(1),
        candidates,
        DuplicateRegistry(job.dedupe, lemmatizer=build_lemmatizer()),
        generator,
        auditor,
        PromptLibrary(),
        stats,
        progress or Progress(),
    )
    return produced, stats


def test_a_lesson_keeps_going_past_six_rounds_while_candidates_remain(
    document, book_path, tmp_path
):
    """The regression: six rounds used to end a lesson with the pool half full.

    Every candidate but the first eight is rejected at audit, so filling four
    places takes far more than six passes. The pool has enough words in it, and
    the lesson has to reach them.
    """
    words = [candidate.term for candidate in pool(30)]
    job = build_job(
        book_path,
        tmp_path / "out",
        vocabulary_per_lesson=4,
        candidates_per_lesson=30,
        lessons=[{"lesson": 1, "start_chapter": 1, "end_chapter": 6}],
    )
    # Reject everything except the last few, so success is only reachable deep
    # into the pool.
    provider = ScriptedProvider(fail_audit=set(words[:-6]))

    produced, stats = fill(document, job, provider, pool(30))

    assert stats.rounds[1] > 6
    assert sum(1 for item in produced if item.status is Status.READY) > 0


def test_a_lesson_stops_when_the_pool_is_spent_and_not_before(
    document, book_path, tmp_path
):
    """Coming up short has to mean the book ran out, so the pool must be empty."""
    words = [candidate.term for candidate in pool(12)]
    job = build_job(
        book_path,
        tmp_path / "out",
        vocabulary_per_lesson=20,
        candidates_per_lesson=20,
        lessons=[{"lesson": 1, "start_chapter": 1, "end_chapter": 6}],
    )
    provider = ScriptedProvider(fail_audit=set(words))

    produced, _ = fill(document, job, provider, pool(12))

    assert len(produced) == 12
    assert all(item.status is not Status.READY for item in produced)


def test_the_budget_stops_a_provider_that_answers_badly_forever(
    document, book_path, tmp_path
):
    """The bound that was actually wanted, and it says which one it was.

    An endpoint that answers every request with something unusable drains the
    pool at full price and produces nothing. The pool still ends the loop, but
    only after paying for all of it, so the budget is what stops it sooner —
    and the note says a provider misbehaved rather than implying the book ran
    short of words.
    """
    from bookengine.vocabulary.pipeline import Progress

    class Collecting(Progress):
        def __init__(self):
            self.notes = []

        def note(self, message):
            self.notes.append(message)

    job = build_job(
        book_path,
        tmp_path / "out",
        vocabulary_per_lesson=4,
        candidates_per_lesson=30,
        lessons=[{"lesson": 1, "start_chapter": 1, "end_chapter": 6}],
        limits={"provider_calls_per_candidate": 1},
    )
    progress = Collecting()
    candidates = pool(30)
    hostile = ScriptedProvider(fail_audit={item.term for item in candidates})

    produced, stats = fill(document, job, hostile, candidates, progress=progress)

    assert len(produced) < len(candidates)
    assert stats.provider_calls[1] >= 30
    assert any("stopped at its budget" in note for note in progress.notes)
    assert any("candidate(s) untried" in note for note in progress.notes)


def test_the_budget_note_is_silent_when_the_pool_is_what_ran_out(
    document, book_path, tmp_path
):
    """Otherwise it sends an operator after a provider that behaved fine."""
    from bookengine.vocabulary.pipeline import Progress

    class Collecting(Progress):
        def __init__(self):
            self.notes = []

        def note(self, message):
            self.notes.append(message)

    job = build_job(
        book_path,
        tmp_path / "out",
        vocabulary_per_lesson=4,
        candidates_per_lesson=30,
        lessons=[{"lesson": 1, "start_chapter": 1, "end_chapter": 6}],
    )
    progress = Collecting()
    candidates = pool(30)
    hostile = ScriptedProvider(fail_audit={item.term for item in candidates})

    produced, stats = fill(document, job, hostile, candidates, progress=progress)

    assert len(produced) == len(candidates)
    assert stats.rounds[1] > 6
    assert progress.notes == []
