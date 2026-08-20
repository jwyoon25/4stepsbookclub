"""The smoke test itself, against a stand-in endpoint that misbehaves on demand.

Every provider adapter here was written against documentation and exercised
against a fake that always cooperates. The smoke command exists to answer what
that cannot: does the key work, does the model id still exist, does the endpoint
honour a schema, and what does it do at its rate limit.

These tests run it against a local HTTP server rather than a mocked client, so
the whole path is real — headers, status codes, JSON parsing, the chain's error
handling — with nothing hosted and no key.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from bookengine.config import LLMConfig, ProviderConfig
from bookengine.llm.smoke import (
    SMOKE_TOTAL,
    SMOKE_WORD,
    render_report,
    smoke_test_all,
    smoke_test_provider,
)

# What the stub endpoint should do with the next request.
BEHAVIOUR = {"kind": "good"}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *arguments):  # keep the test output readable
        pass

    def do_POST(self):  # noqa: N802 - the name http.server requires
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        kind = BEHAVIOUR["kind"]

        if kind == "ratelimited":
            return self._json(429, {"error": {"message": "rate limit reached"}})
        if kind == "unauthorized":
            return self._json(401, {"error": {"message": "invalid api key"}})
        if kind == "outage":
            return self._json(503, {"error": {"message": "upstream unavailable"}})

        if kind == "prose":
            content = "Sure! Happy to help with that."
        elif kind == "wrong":
            content = json.dumps({"echo": "banana", "total": 3})
        else:
            content = json.dumps({"echo": SMOKE_WORD, "total": SMOKE_TOTAL})

        model = "some-other-model" if kind == "substituted" else body.get("model")
        return self._json(
            200,
            {
                "id": "smoke",
                "model": model,
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    def _json(self, status: int, payload: dict):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


@pytest.fixture(scope="module")
def endpoint():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


@pytest.fixture(autouse=True)
def _reset_behaviour():
    BEHAVIOUR["kind"] = "good"
    yield
    BEHAVIOUR["kind"] = "good"


@pytest.fixture
def provider(endpoint, monkeypatch):
    monkeypatch.setenv("SMOKE_TEST_KEY", "not-a-real-key")
    return ProviderConfig(
        provider="stub",
        model="stub-writer-1",
        base_url=endpoint,
        api_key_env="SMOKE_TEST_KEY",
        timeout_seconds=5.0,
    )


# --- the endpoint working --------------------------------------------------


def test_a_working_endpoint_reports_every_stage_it_passed(provider):
    result = smoke_test_provider(provider)

    assert result.ok
    assert result.checks == {
        "authenticated": True,
        "structured_response_parsed": True,
        "echoed_the_prompt": True,
        "did_the_arithmetic": True,
        "reported_a_model_id": True,
        "model_id_matches_request": True,
    }
    assert result.model_reported == "stub-writer-1"


def test_a_working_endpoint_says_how_structured_output_was_requested(provider):
    """A run's log should say whether a real schema or a bare instruction ran."""
    assert smoke_test_provider(provider).schema_mode


# --- the endpoint failing, told apart ---------------------------------------


def test_a_rate_limit_is_reported_as_something_to_wait_out(provider):
    BEHAVIOUR["kind"] = "ratelimited"
    result = smoke_test_provider(provider)

    assert not result.ok
    assert result.retryable is True
    assert "RATE LIMITED" in result.render()


def test_a_rejected_key_is_reported_as_something_to_fix(provider):
    """The distinction the smoke test exists for: waiting will not help here."""
    BEHAVIOUR["kind"] = "unauthorized"
    result = smoke_test_provider(provider)

    assert not result.ok
    assert result.retryable is False
    assert "REFUSED" in result.render()


def test_an_outage_reads_as_temporary(provider):
    BEHAVIOUR["kind"] = "outage"
    result = smoke_test_provider(provider)

    assert result.retryable is True


def test_prose_instead_of_json_is_a_shape_failure_not_an_outage(provider):
    BEHAVIOUR["kind"] = "prose"
    result = smoke_test_provider(provider)

    assert result.reached
    assert not result.parsed
    assert "BAD SHAPE" in result.render()


def test_the_right_shape_with_the_wrong_contents_is_not_a_pass(provider):
    """An endpoint answering from somewhere other than the prompt."""
    BEHAVIOUR["kind"] = "wrong"
    result = smoke_test_provider(provider)

    assert result.parsed
    assert not result.answered_correctly
    assert not result.ok
    assert "WRONG ANSWER" in result.render()


def test_a_substituted_model_is_noticed(provider):
    """Provenance would otherwise record the substitution and nobody would look."""
    BEHAVIOUR["kind"] = "substituted"
    result = smoke_test_provider(provider)

    assert result.ok
    assert result.checks["model_id_matches_request"] is False
    assert result.model_reported == "some-other-model"


def test_a_missing_key_is_reported_without_reaching_the_network(monkeypatch):
    monkeypatch.delenv("ABSENT_SMOKE_KEY", raising=False)
    result = smoke_test_provider(
        ProviderConfig(
            provider="stub",
            model="m",
            base_url="http://127.0.0.1:1/v1",
            api_key_env="ABSENT_SMOKE_KEY",
        )
    )

    assert not result.api_key_present
    assert "ABSENT_SMOKE_KEY" in result.error


# --- and no secrets anywhere in the output ---------------------------------


def test_nothing_in_a_result_carries_the_key(provider, monkeypatch):
    monkeypatch.setenv("SMOKE_TEST_KEY", "sk-do-not-log-this-value")
    result = smoke_test_provider(provider)

    rendered = f"{result.render()} {json.dumps(result.as_dict())}"
    assert "sk-do-not-log-this-value" not in rendered
    assert "SMOKE_TEST_KEY" in json.dumps(result.as_dict())


def test_a_failing_endpoint_does_not_leak_the_key_either(provider, monkeypatch):
    monkeypatch.setenv("SMOKE_TEST_KEY", "sk-do-not-log-this-value")
    BEHAVIOUR["kind"] = "unauthorized"
    result = smoke_test_provider(provider)

    assert "sk-do-not-log-this-value" not in json.dumps(result.as_dict())


# --- what the results mean for a run ---------------------------------------


def llm_config(endpoint: str, **audit) -> LLMConfig:
    shared = {
        "base_url": endpoint,
        "api_key_env": "SMOKE_TEST_KEY",
        "timeout_seconds": 5.0,
    }
    return LLMConfig(
        generator={"provider": "stub", "model": "writer-1", **shared},
        auditor={"provider": "stub", "model": "auditor-1", **shared},
        audit=audit or {},
    )


def test_every_endpoint_a_job_could_reach_is_tested_once(endpoint, monkeypatch):
    monkeypatch.setenv("SMOKE_TEST_KEY", "k")
    config = llm_config(endpoint)
    config.fallbacks = [config.generator]

    results = smoke_test_all(config)

    assert [result.label for result in results] == [
        "stub/writer-1",
        "stub/auditor-1",
    ]


def test_one_reachable_provider_is_flagged_against_a_strict_audit_policy(
    endpoint, monkeypatch
):
    """Better to learn this now than after a hundred generation calls."""
    monkeypatch.setenv("SMOKE_TEST_KEY", "k")
    config = llm_config(endpoint, requirement="provider")

    report = render_report(smoke_test_all(config), config)

    assert "Only one provider is reachable" in report


def test_no_reachable_endpoint_says_the_run_would_not_start(endpoint, monkeypatch):
    monkeypatch.setenv("SMOKE_TEST_KEY", "k")
    BEHAVIOUR["kind"] = "unauthorized"
    config = llm_config(endpoint)

    report = render_report(smoke_test_all(config), config)

    assert "No endpoint answered" in report
