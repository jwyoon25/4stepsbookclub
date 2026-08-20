"""The inference layer: failing over, repairing, caching — without a network."""

from __future__ import annotations

import pytest

from bookengine.config import LLMConfig, ProviderConfig
from bookengine.errors import (
    ConfigError,
    ProviderChainError,
    ProviderError,
    StructuredResponseError,
)
from bookengine.llm.base import Completion, Message
from bookengine.llm.cache import ResponseCache
from bookengine.llm.chain import ProviderChain
from bookengine.llm.registry import build_chains, build_provider
from bookengine.llm.structured import extract_json, generate_structured, parse_into
from bookengine.vocabulary.schemas import EntryDraft

PROMPT = [Message(role="user", content="say something")]


class Stub:
    """A provider that does exactly what a test tells it to."""

    def __init__(self, name, *, answers=None, errors=None):
        self.name = name
        self.model = f"{name}-1"
        self.answers = list(answers or [])
        self.errors = list(errors or [])
        self.calls = 0

    def complete(self, messages, *, json_schema=None, temperature=None, **_):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        text = self.answers.pop(0) if self.answers else "{}"
        return Completion(
            text=text,
            provider=self.name,
            model=self.model,
            prompt_tokens=None,
            completion_tokens=None,
        )


def chain(*providers, cache=None, max_attempts=3):
    return ProviderChain(
        providers=list(providers),
        max_attempts=max_attempts,
        cache=cache,
        sleep=lambda _: None,
        jitter=lambda: 0.5,
    )


# --- the chain -------------------------------------------------------------


def test_a_rate_limit_is_retried_on_the_same_provider():
    limited = Stub(
        "groq",
        errors=[ProviderError("429", provider="groq", retryable=True)],
        answers=["ok"],
    )
    assert chain(limited).complete(PROMPT).text == "ok"
    assert limited.calls == 2


def test_a_bad_key_moves_straight_to_the_next_provider():
    """Retrying a wrong key eight times helps nobody."""
    refused = ProviderError("401", provider="groq", retryable=False)
    broken = Stub("groq", errors=[refused])
    spare = Stub("nvidia", answers=["from the fallback"])

    result = chain(broken, spare).complete(PROMPT)
    assert result.provider == "nvidia"
    assert broken.calls == 1


def test_when_everything_fails_the_error_says_what_each_provider_said():
    quota = ProviderError("quota exceeded", provider="groq", retryable=False)
    bad_key = ProviderError("bad key", provider="nvidia", retryable=False)
    first = Stub("groq", errors=[quota])
    second = Stub("nvidia", errors=[bad_key])

    with pytest.raises(ProviderChainError) as failure:
        chain(first, second).complete(PROMPT)
    message = str(failure.value)
    assert "quota exceeded" in message
    assert "bad key" in message
    assert "llm.fallbacks" in message


def test_a_retry_after_header_is_honoured_and_capped():
    waits = []
    error = ProviderError("429", provider="groq", retryable=True)
    error.retry_after = 9999
    limited = Stub("groq", errors=[error], answers=["ok"])
    link = ProviderChain(
        providers=[limited], sleep=waits.append, jitter=lambda: 0.5
    )

    link.complete(PROMPT)
    assert waits and waits[0] <= 45


def test_an_empty_chain_is_refused():
    with pytest.raises(ProviderChainError):
        ProviderChain(providers=[])


# --- the cache -------------------------------------------------------------


def test_an_identical_call_is_answered_from_the_cache(tmp_path):
    cache = ResponseCache(directory=tmp_path / "llm")
    provider = Stub("groq", answers=["first"])
    link = chain(provider, cache=cache)

    assert link.complete(PROMPT).text == "first"
    again = chain(Stub("groq"), cache=cache).complete(PROMPT)
    assert again.text == "first"
    assert again.cached


def test_a_different_schema_is_a_different_question(tmp_path):
    cache = ResponseCache(directory=tmp_path / "llm")
    chain(Stub("groq", answers=["plain"]), cache=cache).complete(PROMPT)
    other = chain(Stub("groq", answers=["structured"]), cache=cache).complete(
        PROMPT, json_schema={"type": "object"}
    )
    assert other.text == "structured"


def test_a_failure_is_never_cached(tmp_path):
    cache = ResponseCache(directory=tmp_path / "llm")
    with pytest.raises(ProviderChainError):
        down = ProviderError("down", provider="groq", retryable=False)
        chain(Stub("groq", errors=[down]), cache=cache).complete(PROMPT)

    assert chain(Stub("groq", answers=["recovered"]), cache=cache).complete(
        PROMPT
    ).text == "recovered"


def test_a_disabled_cache_stores_nothing(tmp_path):
    cache = ResponseCache(directory=tmp_path / "llm", enabled=False)
    chain(Stub("groq", answers=["first"]), cache=cache).complete(PROMPT)
    assert chain(Stub("groq", answers=["second"]), cache=cache).complete(
        PROMPT
    ).text == "second"


# --- structured output -----------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        'Sure, here you go:\n```\n{"a": 1}\n```',
        'Here is the JSON: {"a": 1} — hope that helps!',
    ],
)
def test_json_is_found_through_whatever_a_free_model_wraps_it_in(reply):
    import json

    assert json.loads(extract_json(reply)) == {"a": 1}


def test_a_brace_inside_a_string_does_not_end_the_object():
    assert extract_json('note: {"s": "}", "n": 2}') == '{"s": "}", "n": 2}'


def test_a_reply_with_no_json_at_all_is_refused():
    with pytest.raises(StructuredResponseError, match="no JSON"):
        extract_json("I'm afraid I can't help with that.")


def test_the_wrong_shape_is_refused_rather_than_half_accepted():
    with pytest.raises(StructuredResponseError):
        parse_into('{"definition": "x"}', EntryDraft)


def test_an_invented_field_is_refused():
    """A model volunteering an `excerpt` must not be half-accepted."""
    payload = (
        '{"definition": "a difficult situation", "korean_meaning": "곤경", '
        '"excerpt_context": "Mara is alone.", "excerpt": "invented text"}'
    )
    with pytest.raises(StructuredResponseError):
        parse_into(payload, EntryDraft)


def test_one_bad_answer_is_repaired_by_showing_the_model_its_own_error():
    good = (
        '{"definition": "a difficult situation", "korean_meaning": "곤경", '
        '"excerpt_context": "Mara is left alone in the hut."}'
    )
    provider = Stub("groq", answers=["not json at all", good])

    draft, completion = generate_structured(chain(provider), PROMPT, EntryDraft)
    assert draft.korean_meaning == "곤경"
    assert provider.calls == 2


def test_a_model_that_never_answers_correctly_fails_with_its_last_reply():
    provider = Stub("groq", answers=["nope"] * 5)
    with pytest.raises(StructuredResponseError) as failure:
        generate_structured(chain(provider), PROMPT, EntryDraft, max_repairs=2)
    assert "nope" in str(failure.value)


# --- the registry ----------------------------------------------------------


def test_an_unknown_provider_still_works_when_the_job_supplies_a_url(monkeypatch):
    monkeypatch.setenv("SOME_KEY", "x")
    provider = build_provider(
        ProviderConfig(
            provider="brand-new-host",
            model="m",
            base_url="https://example.invalid/v1",
            api_key_env="SOME_KEY",
        )
    )
    assert provider.base_url == "https://example.invalid/v1"


def test_an_unknown_provider_without_a_url_says_what_to_add():
    with pytest.raises(ConfigError, match="base_url"):
        build_provider(ProviderConfig(provider="brand-new-host", model="m"))


def test_a_missing_api_key_names_the_variable_to_set(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="GROQ_API_KEY"):
        build_provider(ProviderConfig(provider="groq", model="m"))


def test_both_chains_are_built_and_share_the_fallbacks(monkeypatch, tmp_path):
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("NVIDIA_API_KEY", "y")
    monkeypatch.setenv("CEREBRAS_API_KEY", "z")

    generator, auditor = build_chains(
        LLMConfig(
            generator=ProviderConfig(provider="groq", model="g"),
            auditor=ProviderConfig(provider="nvidia", model="a"),
            fallbacks=[ProviderConfig(provider="cerebras", model="f")],
        ),
        cache_directory=tmp_path,
    )
    assert generator.labels == ["groq/g", "cerebras/f"]
    assert auditor.labels == ["nvidia/a", "cerebras/f"]
