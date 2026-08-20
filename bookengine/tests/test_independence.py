"""Whether the audit was independent, decided from what actually answered.

The engine supports fallbacks so that one dead endpoint does not stop a run.
That creates the case these tests are about: a job naming Groq for writing and
NVIDIA for auditing, where both are down and both chains fall back to Gemini.
The configuration still reads as two providers; one model wrote every entry and
approved its own work.

So independence is computed from the completions that came back, and a run that
did not get it says so instead of inheriting the claim from its job file.
"""

from __future__ import annotations

from bookengine.errors import ProviderError
from bookengine.llm.base import Completion, Message
from bookengine.llm.chain import ProviderChain
from bookengine.prompts import PromptLibrary
from bookengine.vocabulary.audit import (
    independence_of,
    weakest_independence,
)
from bookengine.vocabulary.models import Status, VocabularyItem
from bookengine.vocabulary.pipeline import run_job
from conftest import build_job
from fakes import ScriptedProvider


def item_written_by(generator: tuple[str, str], auditor: tuple[str, str]):
    item = VocabularyItem(lesson=1, term="reluctant", normalized_term="reluctant")
    item.provenance.generator_provider, item.provenance.generator_model = generator
    item.provenance.auditor_provider, item.provenance.auditor_model = auditor
    return item


# --- the three cases the policy has to name --------------------------------


def test_case_a_two_providers_is_provider_level_independence():
    """Groq writes, NVIDIA audits. Different companies, different failures."""
    found = independence_of(
        item_written_by(("groq", "model-a"), ("nvidia", "model-b"))
    )

    assert found.level == "provider"
    assert found.satisfies("provider")
    assert found.satisfies("model")


def test_case_b_a_shared_fallback_is_not_independent_however_it_was_configured():
    """Both primaries down, both chains land on Gemini. One model did both."""
    found = independence_of(
        item_written_by(("gemini", "model-c"), ("gemini", "model-c"))
    )

    assert found.level == "none"
    assert not found.satisfies("provider")
    assert not found.satisfies("model")
    assert found.satisfies("none")


def test_case_c_two_models_on_one_provider_is_model_level_and_no_more():
    """Documented rather than left to be guessed at.

    Two models from one lab share training data and much of their behaviour, so
    this is a weaker second opinion than two providers — real, but not what
    strict mode is asking for.
    """
    found = independence_of(
        item_written_by(("groq", "model-a"), ("groq", "model-b"))
    )

    assert found.level == "model"
    assert found.satisfies("model")
    assert not found.satisfies("provider")


def test_missing_provenance_counts_as_no_independence_at_all():
    """What was not recorded cannot be claimed."""
    assert independence_of(VocabularyItem(1, "x", "x")).level == "none"


def test_a_run_claims_the_weakest_independence_any_of_its_rows_reached():
    """Not the average. One unchecked row is a row nobody checked."""
    items = [
        item_written_by(("groq", "a"), ("nvidia", "b")),
        item_written_by(("groq", "a"), ("groq", "b")),
    ]

    assert weakest_independence(items) == "model"
    items.append(item_written_by(("groq", "a"), ("groq", "a")))
    assert weakest_independence(items) == "none"


# --- and what a run does about it ------------------------------------------


class FailingProvider:
    """A primary that is simply down, so the chain moves to its fallback."""

    def __init__(self, name: str) -> None:
        self.name, self.model = name, "primary-1"

    def complete(self, messages: list[Message], **kwargs) -> Completion:
        raise ProviderError(
            f"{self.name} is unavailable", provider=self.name, retryable=False
        )

    def close(self) -> None:
        pass


def run_with(document, job, generator_providers, auditor_providers):
    return run_job(
        document,
        job,
        ProviderChain(providers=generator_providers, sleep=lambda _: None),
        ProviderChain(providers=auditor_providers, sleep=lambda _: None),
        PromptLibrary(),
    )


def two_provider_job(book_path, output, **overrides):
    return build_job(
        book_path,
        output,
        llm={
            "generator": {"provider": "groq", "model": "model-a"},
            "auditor": {"provider": "nvidia", "model": "model-b"},
            **overrides,
        },
    )


def test_a_run_that_kept_two_providers_reports_provider_independence(
    document, book_path, tmp_path
):
    job = two_provider_job(book_path, tmp_path / "out")
    writer = ScriptedProvider(name="groq", model="model-a")

    result = run_with(
        document, job, [writer], [ScriptedProvider(name="nvidia", model="model-b")]
    )

    assert result.ok, result.report.render()
    assert result.stats.audit_independence_actual == "provider"
    assert result.report.audit_not_independent == 0


def test_a_shared_fallback_is_reported_even_though_the_job_names_two(
    document, book_path, tmp_path
):
    """The case the configured-only answer got wrong.

    Both primaries fail, both chains fall back to one Gemini endpoint. The job
    file still says groq and nvidia; the run says what happened.
    """
    job = two_provider_job(book_path, tmp_path / "out")
    shared = ScriptedProvider(name="gemini", model="model-c")

    result = run_with(
        document,
        job,
        [FailingProvider("groq"), shared],
        [FailingProvider("nvidia"), shared],
    )

    assert job.llm.configured_independence == "provider"
    assert result.stats.audit_independence_configured == "provider"
    assert result.stats.audit_independence_actual == "none"


def test_rows_a_shared_fallback_audited_are_not_exported_as_proved(
    document, book_path, tmp_path
):
    """`needs_review` is the default, and READY is what it takes away."""
    job = two_provider_job(book_path, tmp_path / "out")
    shared = ScriptedProvider(name="gemini", model="model-c")

    result = run_with(
        document,
        job,
        [FailingProvider("groq"), shared],
        [FailingProvider("nvidia"), shared],
    )

    assert not result.ok
    assert result.ready == []
    assert any(item.status is Status.NEEDS_REVIEW for item in result.items)
    assert "audited by the same endpoint that wrote them" in result.report.render()


def test_the_relaxed_requirement_accepts_two_models_on_one_provider(
    document, book_path, tmp_path
):
    job = two_provider_job(
        book_path, tmp_path / "out", audit={"requirement": "model"}
    )

    result = run_with(
        document,
        job,
        [ScriptedProvider(name="groq", model="model-a")],
        [ScriptedProvider(name="groq", model="model-b")],
    )

    assert result.ok, result.report.render()
    assert result.stats.audit_independence_actual == "model"


def test_the_relaxed_requirement_still_refuses_one_model_doing_both(
    document, book_path, tmp_path
):
    """Relaxed is not off. A model marking its own work is not a second opinion."""
    job = two_provider_job(
        book_path, tmp_path / "out", audit={"requirement": "model"}
    )
    shared = ScriptedProvider(name="groq", model="model-a")

    result = run_with(document, job, [shared], [shared])

    assert not result.ok
    assert result.report.audit_not_independent > 0


def test_a_run_may_opt_out_but_the_artifact_still_says_what_happened(
    document, book_path, tmp_path
):
    """`allow` exports the work; it does not rewrite the record."""
    job = two_provider_job(
        book_path,
        tmp_path / "out",
        audit={"requirement": "provider", "on_shared": "allow"},
    )
    shared = ScriptedProvider(name="gemini", model="model-c")

    result = run_with(
        document,
        job,
        [FailingProvider("groq"), shared],
        [FailingProvider("nvidia"), shared],
    )

    assert result.ok, result.report.render()
    assert result.stats.audit_independence_actual == "none"
    assert result.report.audit_independence["actual"] == "none"


def test_failing_the_run_names_the_rows_rather_than_only_counting_them(
    document, book_path, tmp_path
):
    job = two_provider_job(
        book_path,
        tmp_path / "out",
        audit={"requirement": "provider", "on_shared": "fail"},
    )
    shared = ScriptedProvider(name="gemini", model="model-c")

    result = run_with(
        document,
        job,
        [FailingProvider("groq"), shared],
        [FailingProvider("nvidia"), shared],
    )

    assert not result.ok
    assert result.report.item_failures
    assert any("gemini/model-c" in failure for failure in result.report.item_failures)


def test_the_audit_artifact_records_the_pairings_that_actually_happened(
    document, book_path, tmp_path
):
    from bookengine.export.artifacts import build_audit_summary

    job = two_provider_job(book_path, tmp_path / "out")
    result = run_with(
        document,
        job,
        [ScriptedProvider(name="groq", model="model-a")],
        [ScriptedProvider(name="nvidia", model="model-b")],
    )
    summary = build_audit_summary(
        result.items, job=job, document=document, run=result.stats.as_dict()
    )["audit"]

    assert summary["independence_actual"] == "provider"
    assert summary["actual_pairings"] == [
        {"generator": "groq/model-a", "auditor": "nvidia/model-b", "items": 8}
    ]
