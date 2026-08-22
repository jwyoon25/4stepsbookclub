"""What each generator stage is allowed to spend on its answer.

The ceiling is not free. Groq's free tier charges its per-minute token
allowance for what a request *reserves* — input plus `max_output_tokens` — not
for what it uses, so a stage asking for four thousand tokens to return an
integer pays for four thousand tokens on every call. Measured on
`openai/gpt-oss-120b` against fixture prose, the four stages answer in 253 to
3,675 tokens depending on which one and how many items it was given, so one
number for all of them is either wasteful or too small.

These tests pin two things: that every stage passes a ceiling at all, and that
the ceilings still clear what the stages were measured needing.
"""

from __future__ import annotations

import pytest

from bookengine.llm.base import Completion, Message
from bookengine.vocabulary.candidates import (
    candidate_output_tokens,
    ranking_output_tokens,
)
from bookengine.vocabulary.entries import ENTRY_OUTPUT_TOKENS
from bookengine.vocabulary.pipeline import OCCURRENCE_OUTPUT_TOKENS

# Groq's free-tier allowance, and the input each stage measured at, so the sums
# below are the real ones rather than a guess.
GROQ_TOKENS_PER_MINUTE = 8_000

# stage, measured input, measured largest answer over three runs
MEASURED = [
    ("ranking, 25 candidates", 3_323, 3_675, lambda: ranking_output_tokens(25)),
    ("ranking, 15 candidates", 2_400, 2_205, lambda: ranking_output_tokens(15)),
    ("candidates, 25 words", 2_891, 3_000, lambda: candidate_output_tokens(25)),
    ("occurrence choice", 1_000, 304, lambda: OCCURRENCE_OUTPUT_TOKENS),
    ("entry draft", 1_478, 410, lambda: ENTRY_OUTPUT_TOKENS),
]


@pytest.mark.parametrize(
    "name, sent, answered, budget", MEASURED, ids=[row[0] for row in MEASURED]
)
def test_every_stage_clears_what_it_was_measured_needing(name, sent, answered, budget):
    """With headroom, because a reasoning model's output varies run to run.

    Ranking answered in 2,681 and 3,675 tokens on two runs of the same prompt.
    A ceiling set at the average would truncate half the time.
    """
    assert budget() > answered


@pytest.mark.parametrize(
    "name, sent, answered, budget", MEASURED, ids=[row[0] for row in MEASURED]
)
def test_no_stage_reserves_more_than_a_minute_of_groq(name, sent, answered, budget):
    """A request over the allowance is refused outright, not slowed down.

    Groq answers one that does not fit with HTTP 413 naming the limit, so this
    is the difference between a stage that paces and a stage that never runs.
    """
    assert sent + budget() <= GROQ_TOKENS_PER_MINUTE


def test_the_batched_stages_scale_with_what_they_were_given():
    """Both answer with one object per item, so a flat number fits one batch."""
    assert ranking_output_tokens(50) > ranking_output_tokens(25)
    assert ranking_output_tokens(25) > ranking_output_tokens(10)
    assert candidate_output_tokens(40) > candidate_output_tokens(20)


def test_a_batch_of_one_still_gets_room_to_think():
    """The floor is the model's own preamble, which does not shrink to nothing."""
    assert ranking_output_tokens(1) > 500
    assert candidate_output_tokens(1) > 500
    assert ranking_output_tokens(0) == ranking_output_tokens(1)


def test_the_two_fixed_stages_are_far_below_the_provider_default():
    """Neither can grow with the input: both are schema-capped fields.

    `OccurrenceChoice` is an integer and a 240-character sentence;
    `EntryDraft` is three fields capped at 600, 100 and 700 characters. The
    4,096 provider default was reserving more than five thousand tokens of an
    eight thousand token minute to return them.
    """
    assert OCCURRENCE_OUTPUT_TOKENS < 1_024
    assert ENTRY_OUTPUT_TOKENS <= 1_024


# --- and that the call sites actually pass them ---------------------------


class Recorder:
    """A provider that records what it was asked for and answers trivially."""

    name, model = "recorder", "recorder-1"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.budgets: list[int | None] = []

    def complete(self, messages: list[Message], *, json_schema=None,
                 temperature=None, max_output_tokens=None) -> Completion:
        self.budgets.append(max_output_tokens)
        return Completion(text=self.reply, provider=self.name, model=self.model,
                          prompt_tokens=None, completion_tokens=None)

    def close(self) -> None:
        pass


def test_the_entry_stage_asks_for_its_own_budget(document, job):
    from bookengine.config import ExcerptConfig
    from bookengine.llm.chain import ProviderChain
    from bookengine.prompts import PromptLibrary
    from bookengine.source.search import find_occurrences
    from bookengine.vocabulary.entries import draft_entry
    from bookengine.vocabulary.models import VocabularyItem
    from bookengine.vocabulary.quotes import build_excerpt

    occurrence = find_occurrences(document, "predicament")[0]
    candidate = build_excerpt(document, occurrence, ExcerptConfig())
    item = VocabularyItem(lesson=1, term="predicament", normalized_term="predicament")
    item.locator, item.excerpt = candidate.locator, candidate.text

    recorder = Recorder(
        '{"definition": "d", "korean_meaning": "뜻", "excerpt_context": "c"}'
    )
    draft_entry(document, job, item, ProviderChain(providers=[recorder]),
                PromptLibrary())

    assert recorder.budgets == [ENTRY_OUTPUT_TOKENS]


def test_the_occurrence_stage_asks_for_its_own_budget(document, job):
    from bookengine.config import ExcerptConfig
    from bookengine.llm.chain import ProviderChain
    from bookengine.prompts import PromptLibrary
    from bookengine.vocabulary.pipeline import _occurrence_chooser
    from bookengine.vocabulary.quotes import excerpt_candidates

    shortlist = excerpt_candidates(document, "certain", range(1, 13), ExcerptConfig())
    if len(shortlist) < 2:
        pytest.skip("needs a word with more than one usable passage")

    recorder = Recorder('{"index": 0, "reason": "it teaches the word"}')
    chooser = _occurrence_chooser(job, document, ProviderChain(providers=[recorder]),
                                 PromptLibrary(), "a sense")
    chooser("certain", shortlist)

    assert recorder.budgets == [OCCURRENCE_OUTPUT_TOKENS]
