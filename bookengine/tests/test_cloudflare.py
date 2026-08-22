"""The Workers AI adapter: its URL, its errors, and what it must never say.

Cloudflare is the OpenAI shape behind an account-scoped URL, so most of what
this adapter does is already covered by the OpenAI adapter's tests. What is new
is the URL — built from an environment variable rather than a constant — and a
second credential to keep out of the output.
"""

from __future__ import annotations

import json

import httpx
import pytest

from bookengine.config import ProviderConfig
from bookengine.errors import ConfigError, ProviderError
from bookengine.llm.base import Message
from bookengine.llm.cloudflare import (
    ACCOUNT_ENVIRONMENT,
    API_KEY_ENVIRONMENT,
    CloudflareProvider,
)
from bookengine.llm.registry import build_provider

ACCOUNT = "acct-0123456789abcdef"
TOKEN = "cf-token-do-not-log-this"
MODEL = "@cf/google/gemma-4-26b-a4b-it"

ANSWER = {
    "id": "x",
    "model": MODEL,
    "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 58, "completion_tokens": 12, "neurons": 4.3181},
}


@pytest.fixture(autouse=True)
def _credentials(monkeypatch):
    monkeypatch.setenv(ACCOUNT_ENVIRONMENT, ACCOUNT)
    monkeypatch.setenv(API_KEY_ENVIRONMENT, TOKEN)


def provider(handler, **overrides) -> CloudflareProvider:
    config = ProviderConfig(
        **{"provider": "cloudflare", "model": MODEL, "timeout_seconds": 5.0,
           **overrides}
    )
    return CloudflareProvider(
        config, client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def answering(payload=ANSWER, status=200, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        body = payload if isinstance(payload, (dict, list)) else payload
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=body)
    return handler


def ask(endpoint: CloudflareProvider):
    return endpoint.complete([Message(role="user", content="hello")])


# --- the URL ---------------------------------------------------------------


def test_the_account_id_is_taken_from_the_environment():
    seen: list[httpx.Request] = []
    ask(provider(answering(seen=seen)))

    assert str(seen[0].url) == (
        f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}"
        "/ai/v1/chat/completions"
    )


def test_a_missing_account_id_names_the_variable_and_stops(monkeypatch):
    monkeypatch.delenv(ACCOUNT_ENVIRONMENT, raising=False)

    with pytest.raises(ConfigError) as failure:
        CloudflareProvider(ProviderConfig(provider="cloudflare", model=MODEL))

    assert ACCOUNT_ENVIRONMENT in str(failure.value)


def test_an_explicit_base_url_still_wins():
    """So a Workers AI gateway or a proxy needs no code change."""
    seen: list[httpx.Request] = []
    ask(provider(answering(seen=seen), base_url="https://gateway.example/v1"))

    assert str(seen[0].url) == "https://gateway.example/v1/chat/completions"


def test_the_registry_builds_it_by_name():
    endpoint = build_provider(ProviderConfig(provider="cloudflare", model=MODEL))
    assert isinstance(endpoint, CloudflareProvider)


# --- the credential --------------------------------------------------------


def test_the_token_is_sent_as_a_bearer_credential():
    seen: list[httpx.Request] = []
    ask(provider(answering(seen=seen)))

    assert seen[0].headers["Authorization"] == f"Bearer {TOKEN}"


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_no_error_from_any_status_repeats_the_token(status):
    """The one thing an error message must never be helpful about."""
    endpoint = provider(answering({"errors": [{"message": "no"}]}, status=status))

    with pytest.raises(ProviderError) as failure:
        ask(endpoint)

    assert TOKEN not in str(failure.value)
    assert TOKEN not in repr(failure.value)


def test_a_rejected_token_names_the_variable_rather_than_the_value():
    endpoint = provider(answering({"errors": [{"message": "bad"}]}, status=403))

    with pytest.raises(ProviderError) as failure:
        ask(endpoint)

    message = str(failure.value)
    assert API_KEY_ENVIRONMENT in message
    assert TOKEN not in message


# --- the answers -----------------------------------------------------------


def test_a_good_answer_carries_its_provenance_and_its_meter():
    completion = ask(provider(answering()))

    assert completion.provider == "cloudflare"
    assert completion.model == MODEL
    assert completion.prompt_tokens == 58
    assert completion.completion_tokens == 12
    assert completion.usage_units == pytest.approx(4.3181)


def test_a_substituted_model_is_recorded_as_what_answered():
    served = dict(ANSWER, model="@cf/meta/llama-3.3-70b-instruct-fp8-fast")
    completion = ask(provider(answering(served)))

    assert completion.model == "@cf/meta/llama-3.3-70b-instruct-fp8-fast"


def test_a_model_that_reports_no_meter_is_not_an_error():
    payload = dict(ANSWER, usage={"prompt_tokens": 1, "completion_tokens": 1})
    assert ask(provider(answering(payload))).usage_units is None


# --- the failures, told apart ----------------------------------------------


@pytest.mark.parametrize(
    "status, retryable",
    [(401, False), (403, False), (429, True), (500, True), (503, True)],
)
def test_each_failure_is_classified_the_way_the_chain_needs(status, retryable):
    """A quota is worth waiting out; a rejected token never is."""
    endpoint = provider(answering({"errors": [{"message": "x"}]}, status=status))

    with pytest.raises(ProviderError) as failure:
        ask(endpoint)

    assert failure.value.retryable is retryable


def test_a_limit_carries_cloudflares_own_words_and_stays_retryable():
    """`status_error` prints hints only where waiting will not help, so the
    useful content at 429 is what Cloudflare itself said."""
    endpoint = provider(answering({"errors": [{"message": "out of neurons"}]},
                                  status=429))

    with pytest.raises(ProviderError) as failure:
        ask(endpoint)

    assert "out of neurons" in str(failure.value)
    assert failure.value.retryable is True


def test_an_unknown_model_points_at_the_catalogue():
    endpoint = provider(answering({"errors": [{"message": "no model"}]}, status=404))

    with pytest.raises(ProviderError) as failure:
        ask(endpoint)

    assert "@cf/" in str(failure.value)


def test_a_body_that_is_not_json_is_a_provider_error_not_a_crash():
    with pytest.raises(ProviderError):
        ask(provider(answering("<html>gateway</html>")))


def test_an_answer_with_no_choices_is_refused():
    with pytest.raises(ProviderError):
        ask(provider(answering({"model": MODEL, "choices": []})))


def test_an_empty_completion_explains_the_reasoning_budget():
    """GLM burns its whole budget thinking when the ceiling is too low."""
    payload = {
        "model": MODEL,
        "choices": [{"message": {"content": None}, "finish_reason": "length"}],
        "usage": {"prompt_tokens": 45, "completion_tokens": 256},
    }
    with pytest.raises(ProviderError) as failure:
        ask(provider(answering(payload)))

    assert "max_output_tokens" in str(failure.value)


def test_a_json_schema_request_is_sent_in_the_openai_shape():
    seen: list[httpx.Request] = []
    endpoint = provider(answering(seen=seen))
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}

    endpoint.complete([Message(role="user", content="hi")], json_schema=schema)

    body = json.loads(seen[0].content)
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == schema
    assert body["model"] == MODEL
    assert body["stream"] is False
