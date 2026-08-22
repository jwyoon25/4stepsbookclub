"""Whether the largest request a job makes is one its generator will accept.

Ranking is the biggest single call this engine makes: one prompt carrying every
candidate in a batch, and an answer carrying one object per candidate back. On
a free endpoint it is therefore the stage that meets a per-request ceiling
first — and a provider that will not take it answers with a status code rather
than a smaller reply.

Groq refuses one with `HTTP 413 … on tokens per minute (TPM): Limit 8000,
Requested 13477`. That is not a rate to wait out; the request never fits. So it
is worth catching before a run has built a chapter map and harvested a pool.
"""

from __future__ import annotations

import pytest

from bookengine.config import JobConfig
from bookengine.errors import ConfigError
from bookengine.vocabulary.candidates import (
    ranking_request_tokens,
    validate_generator_budget,
)
from conftest import build_job

# Groq's free-tier ceiling, measured from a live 413 rather than documentation.
GROQ_CEILING = 8_000

# Measured `prompt_tokens` on openai/gpt-oss-120b, three batch sizes.
MEASURED_INPUT = {15: 2_619, 20: 3_015, 25: 3_323}


def job_with(book_path, tmp_path, **candidates) -> JobConfig:
    return build_job(
        book_path,
        tmp_path / "out",
        candidates=candidates,
        llm={
            "generator": {
                "provider": "groq",
                "model": "openai/gpt-oss-120b",
                "max_request_tokens": GROQ_CEILING,
            },
            "auditor": {
                "provider": "cloudflare",
                "model": "@cf/zai-org/glm-4.7-flash",
            },
        },
    )


# --- the estimate itself ---------------------------------------------------


@pytest.mark.parametrize("batch, measured", sorted(MEASURED_INPUT.items()))
def test_the_estimate_is_not_below_what_was_actually_sent(batch, measured):
    """An estimator used to refuse work must err towards over-counting."""
    assert ranking_request_tokens(batch) > measured


@pytest.mark.parametrize("batch", [15, 20, 25])
def test_the_batches_measured_working_are_not_refused(batch):
    """All three were sent live and accepted. Refusing them would be a bug."""
    assert ranking_request_tokens(batch) <= GROQ_CEILING


def test_the_batch_groq_actually_refused_is_predicted_to_not_fit():
    """Groq reported 13,477 for a batch of fifty. The estimate says 13,762."""
    assert ranking_request_tokens(50) > GROQ_CEILING


def test_the_estimate_grows_with_the_batch():
    assert ranking_request_tokens(50) > ranking_request_tokens(25)
    assert ranking_request_tokens(25) > ranking_request_tokens(15)


# --- what the production configuration can and cannot attempt --------------


def test_the_maze_runner_job_cannot_attempt_a_batch_of_fifty():
    """The regression this whole pass exists for.

    The shipped configuration used to carry the 50 that Groq refuses, so every
    ranking batch of a real run would have failed.
    """
    import os

    from bookengine.config import load_job

    os.environ.setdefault("CLOUDFLARE_AUDIT_MODEL", "@cf/zai-org/glm-4.7-flash")
    job = load_job("configs/the-maze-runner.yaml")

    assert job.llm.generator.provider == "mistral"
    assert job.llm.generator.model == "mistral-large-2512"
    assert job.candidates.rank_batch < 50
    assert ranking_request_tokens(job.candidates.rank_batch) <= (
        job.llm.generator.max_request_tokens or 0
    )
    groq = next(item for item in job.llm.fallbacks if item.provider == "groq")
    assert ranking_request_tokens(job.candidates.rank_batch) <= (
        groq.max_request_tokens or 0
    )
    assert validate_generator_budget(job) == []


def test_the_shipped_default_also_fits_the_primary_generator():
    """A future job that configures nothing must not inherit a broken batch."""
    from bookengine.config import CandidateConfig

    assert ranking_request_tokens(CandidateConfig().rank_batch) <= GROQ_CEILING


def test_a_job_asking_for_fifty_is_refused_before_anything_is_called(
    book_path, tmp_path
):
    with pytest.raises(ConfigError) as failure:
        validate_generator_budget(job_with(book_path, tmp_path, rank_batch=50))

    message = str(failure.value)
    assert "rank_batch" in message
    assert "8,000" in message


def test_the_refusal_names_a_batch_size_that_would_work(book_path, tmp_path):
    """An error an operator can act on names the fix, not just the problem."""
    with pytest.raises(ConfigError) as failure:
        validate_generator_budget(job_with(book_path, tmp_path, rank_batch=50))

    suggested = int(str(failure.value).rsplit("to ", 1)[1].split()[0])
    assert ranking_request_tokens(suggested) <= GROQ_CEILING
    assert ranking_request_tokens(suggested + 1) > GROQ_CEILING


def test_a_batch_that_only_just_fits_is_flagged_rather_than_refused(
    book_path, tmp_path
):
    """25 fits and has ninety tokens spare on this book's heaviest lesson.

    Refusing it would be wrong — it works. Saying nothing would also be wrong.
    """
    notes = validate_generator_budget(job_with(book_path, tmp_path, rank_batch=25))

    assert any("to spare" in note for note in notes)


def test_a_comfortable_batch_says_nothing(book_path, tmp_path):
    assert validate_generator_budget(job_with(book_path, tmp_path, rank_batch=15)) == []


def test_an_endpoint_with_no_declared_ceiling_is_not_second_guessed(
    book_path, tmp_path
):
    """Inventing a limit for an unmeasured endpoint would refuse working jobs."""
    job = build_job(
        book_path,
        tmp_path / "out",
        candidates={"rank_batch": 200},
        llm={
            "generator": {"provider": "somebody-new", "model": "big"},
            "auditor": {"provider": "cloudflare", "model": "@cf/x"},
        },
    )

    assert validate_generator_budget(job) == []


def test_model_led_candidate_mode_is_flagged_on_a_small_endpoint(
    book_path, tmp_path
):
    """Its 9,000-character default does not fit either, and is not the path
    this engine uses — so it is named rather than refused."""
    notes = validate_generator_budget(
        job_with(book_path, tmp_path, rank_batch=15, mode="model")
    )

    assert any("chunk_characters" in note for note in notes)


def test_harvest_mode_is_not_flagged_for_it(book_path, tmp_path):
    notes = validate_generator_budget(
        job_with(book_path, tmp_path, rank_batch=15, mode="harvest")
    )

    assert not any("chunk_characters" in note for note in notes)
