"""Which endpoints a workbook can reach, and which it must not.

Two separate guarantees live here. The zero-cost one is about what may be in
the route at all: a job naming an endpoint this deployment has classified as
paid does not load. The independence one is about what actually answered, and
it is enforced after the fact, from provenance — so a chain that falls back
onto the generator's own provider is caught even though nothing in routing
tried to avoid it.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from bookengine.config import LLMConfig
from bookengine.errors import ProviderError
from bookengine.llm.base import Completion, Message
from bookengine.llm.chain import ProviderChain
from bookengine.llm.registry import build_chains
from bookengine.prompts import PromptLibrary
from bookengine.vocabulary.models import Status
from bookengine.vocabulary.pipeline import run_job
from conftest import build_job
from fakes import ScriptedProvider

GROQ = {"provider": "groq", "model": "openai/gpt-oss-120b"}
CLOUDFLARE = {"provider": "cloudflare", "model": "@cf/google/gemma-4-26b-a4b-it"}
GEMINI = {"provider": "gemini", "model": "gemini-3.7-flash"}
NVIDIA = {"provider": "nvidia", "model": "nvidia/nemotron-3-super-120b-a12b"}


# --- what may be in the route at all ---------------------------------------


def test_the_normal_route_is_the_two_free_providers_and_a_free_fallback():
    config = LLMConfig(generator=GROQ, auditor=CLOUDFLARE, fallbacks=[GEMINI])

    assert config.configured_independence == "provider"
    assert all(
        provider.cost == "free"
        for provider in (config.generator, config.auditor, *config.fallbacks)
    )


@pytest.mark.parametrize("slot", ["generator", "auditor"])
def test_a_paid_endpoint_cannot_be_a_primary(slot):
    """The rule that "a workbook costs nothing" should survive a bad afternoon."""
    paid = {"provider": "openai", "model": "gpt-4o", "cost": "paid"}
    config = {"generator": GROQ, "auditor": CLOUDFLARE, slot: paid}

    with pytest.raises(ValidationError) as failure:
        LLMConfig(**config)
    assert "cost: free" in str(failure.value)


def test_a_paid_endpoint_cannot_be_a_fallback_either():
    """Which is where it would actually get added, on the third retry."""
    with pytest.raises(ValidationError):
        LLMConfig(
            generator=GROQ,
            auditor=CLOUDFLARE,
            fallbacks=[GEMINI, {"provider": "openai", "model": "o", "cost": "paid"}],
        )


def test_a_paid_endpoint_may_still_be_named_for_benchmarking():
    """Naming it is how somebody compares against it. Routing to it is not."""
    config = LLMConfig(
        generator=GROQ,
        auditor=CLOUDFLARE,
        benchmark=[{"provider": "openai", "model": "gpt-4o", "cost": "paid"}],
    )
    assert config.benchmark[0].cost == "paid"


# --- and which of them a run can reach -------------------------------------


def chains(**overrides):
    config = LLMConfig(
        generator=GROQ, auditor=CLOUDFLARE, fallbacks=[GEMINI], **overrides
    )
    generator, auditor = build_chains(config)
    try:
        return generator.labels, auditor.labels
    finally:
        generator.close()
        auditor.close()


def test_a_benchmark_endpoint_is_in_no_chain():
    """There is no path from `llm.benchmark` into a chain. That is the whole
    mechanism — not a flag consulted at call time, an absence."""
    generator, auditor = chains(benchmark=[NVIDIA])

    assert not any("nvidia" in label for label in generator + auditor)


def test_the_generator_starts_at_groq_and_the_auditor_at_cloudflare():
    generator, auditor = chains()

    assert generator[0].startswith("groq/")
    assert auditor[0].startswith("cloudflare/")


def test_both_chains_share_the_fallback():
    """Which is what makes the independence gate necessary rather than tidy."""
    generator, auditor = chains()

    assert generator[-1].startswith("gemini/")
    assert auditor[-1].startswith("gemini/")


# --- independence, decided from what answered ------------------------------


class Down:
    """A primary that is simply unavailable."""

    def __init__(self, name: str, model: str) -> None:
        self.name, self.model = name, model

    def complete(self, messages: list[Message], **kwargs) -> Completion:
        raise ProviderError(f"{self.name} is unavailable",
                            provider=self.name, retryable=False)

    def close(self) -> None:
        pass


def run(document, job, generator_chain, auditor_chain):
    return run_job(document, job,
                   ProviderChain(providers=generator_chain, sleep=lambda _: None),
                   ProviderChain(providers=auditor_chain, sleep=lambda _: None),
                   PromptLibrary())


@pytest.fixture
def two_provider_job(book_path, tmp_path):
    return build_job(book_path, tmp_path / "out",
                     llm={"generator": GROQ, "auditor": CLOUDFLARE})


def test_normal_case_groq_writes_and_cloudflare_audits(document, two_provider_job):
    result = run(document, two_provider_job,
                 [ScriptedProvider(name="groq", model="openai/gpt-oss-120b")],
                 [ScriptedProvider(name="cloudflare", model="@cf/google/gemma-4")])

    assert result.ok, result.report.render()
    assert result.stats.audit_independence_actual == "provider"


def test_groq_down_gemini_writes_and_cloudflare_still_audits(
    document, two_provider_job
):
    result = run(
        document, two_provider_job,
        [Down("groq", "openai/gpt-oss-120b"),
         ScriptedProvider(name="gemini", model="gemini-3.7-flash")],
        [ScriptedProvider(name="cloudflare", model="@cf/google/gemma-4")],
    )

    assert result.ok, result.report.render()
    assert result.stats.audit_independence_actual == "provider"


def test_cloudflare_down_groq_writes_and_gemini_audits(document, two_provider_job):
    result = run(
        document, two_provider_job,
        [ScriptedProvider(name="groq", model="openai/gpt-oss-120b")],
        [Down("cloudflare", "@cf/google/gemma-4"),
         ScriptedProvider(name="gemini", model="gemini-3.7-flash")],
    )

    assert result.ok, result.report.render()
    assert result.stats.audit_independence_actual == "provider"


def test_both_falling_back_to_gemini_cannot_produce_a_ready_row(
    document, two_provider_job
):
    """The case the shared fallback list creates, and the gate that catches it.

    Routing does not currently steer the auditor away from the generator's
    provider; it is caught afterwards, from provenance, which is enough because
    the consequence is that nothing exports rather than that something wrong
    does.
    """
    shared = ScriptedProvider(name="gemini", model="gemini-3.7-flash")
    result = run(
        document, two_provider_job,
        [Down("groq", "openai/gpt-oss-120b"), shared],
        [Down("cloudflare", "@cf/google/gemma-4"), shared],
    )

    assert not result.ok
    assert result.ready == []
    assert result.stats.audit_independence_actual == "none"
    assert any(item.status is Status.NEEDS_REVIEW for item in result.items)
