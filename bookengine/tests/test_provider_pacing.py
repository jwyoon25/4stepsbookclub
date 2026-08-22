"""Deterministic request-start pacing at the shared provider boundary."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from bookengine.config import ProviderConfig, load_job
from bookengine.llm.base import Message, RequestPacer
from bookengine.llm.chain import ProviderChain
from bookengine.llm.openai_compatible import OpenAICompatibleProvider


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def successful(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        request=request,
        headers={
            "X-RateLimit-Remaining": "3",
            "X-RateLimit-Limit-Req-Minute": "4",
        },
        json={
            "model": "mistral-large-2512",
            "choices": [
                {"message": {"content": json.dumps({"ok": True})},
                 "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        },
    )


def endpoint(monkeypatch, handler, clock: FakeClock, *, interval: float = 15.0):
    monkeypatch.setenv("MISTRAL_API_KEY", "synthetic-test-key")
    pacer = RequestPacer(
        interval, monotonic=clock.monotonic, sleep=clock.sleep
    )
    return OpenAICompatibleProvider(
        ProviderConfig(
            provider="mistral",
            model="mistral-large-2512",
            min_request_interval_seconds=interval,
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        pacer=pacer,
    )


def test_consecutive_requests_are_proactively_spaced(monkeypatch):
    clock = FakeClock()
    starts: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        starts.append(clock.monotonic())
        return successful(request)

    provider = endpoint(monkeypatch, handler, clock)
    try:
        provider.complete([Message(role="user", content="first")])
        provider.complete([Message(role="user", content="second")])
    finally:
        provider.close()

    assert starts == [0.0, 15.0]
    assert clock.sleeps == [15.0]


def test_ranking_occurrence_and_entry_share_one_provider_schedule(monkeypatch):
    clock = FakeClock()
    starts: list[tuple[str, float]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        stage = body["messages"][0]["content"]
        starts.append((stage, clock.monotonic()))
        return successful(request)

    provider = endpoint(monkeypatch, handler, clock)
    try:
        for stage in ("ranking", "occurrence", "entry"):
            provider.complete([Message(role="user", content=stage)])
    finally:
        provider.close()

    assert starts == [
        ("ranking", 0.0),
        ("occurrence", 15.0),
        ("entry", 30.0),
    ]


def test_longer_retry_after_controls_the_retry_start(monkeypatch):
    clock = FakeClock()
    starts: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        starts.append(clock.monotonic())
        if len(starts) == 1:
            return httpx.Response(
                429,
                request=request,
                headers={"Retry-After": "31"},
                json={"error": {"message": "synthetic rate limit"}},
            )
        return successful(request)

    provider = endpoint(monkeypatch, handler, clock)
    chain = ProviderChain(
        providers=[provider], max_attempts=2, sleep=clock.sleep
    )
    try:
        chain.complete([Message(role="user", content="retry")])
    finally:
        chain.close()

    assert starts == [0.0, 31.0]
    assert clock.sleeps == [31.0]


def test_shorter_retry_after_cannot_bypass_provider_spacing(monkeypatch):
    clock = FakeClock()
    starts: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        starts.append(clock.monotonic())
        if len(starts) == 1:
            return httpx.Response(
                429,
                request=request,
                headers={"Retry-After": "5"},
                json={"error": {"message": "synthetic rate limit"}},
            )
        return successful(request)

    provider = endpoint(monkeypatch, handler, clock)
    chain = ProviderChain(
        providers=[provider], max_attempts=2, sleep=clock.sleep
    )
    try:
        chain.complete([Message(role="user", content="retry")])
    finally:
        chain.close()

    assert starts == [0.0, 15.0]
    assert clock.sleeps == [5.0, 10.0]


def test_provider_without_configured_pacing_keeps_current_behavior(monkeypatch):
    clock = FakeClock()
    starts: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        starts.append(clock.monotonic())
        return successful(request)

    provider = endpoint(monkeypatch, handler, clock, interval=0.0)
    try:
        provider.complete([Message(role="user", content="one")])
        provider.complete([Message(role="user", content="two")])
    finally:
        provider.close()

    assert starts == [0.0, 0.0]
    assert clock.sleeps == []


def test_safe_rate_limit_response_headers_are_retained(monkeypatch):
    clock = FakeClock()
    provider = endpoint(monkeypatch, successful, clock, interval=0.0)
    try:
        provider.complete([Message(role="user", content="headers")])
    finally:
        provider.close()

    assert provider.rate_limit_headers == {
        "x-ratelimit-remaining": "3",
        "x-ratelimit-limit-req-minute": "4",
    }


def test_evaluation_job_is_mistral_only_with_cloudflare_auditor():
    configs = Path(__file__).parents[1] / "configs"
    job = load_job(configs / "the-maze-runner-lesson1-mistral-eval.yaml")
    production = load_job(configs / "the-maze-runner-lesson1.yaml")

    assert job.llm.generator.label == "mistral/mistral-large-2512"
    assert job.llm.auditor.label == "cloudflare/@cf/zai-org/glm-4.7-flash"
    assert job.llm.fallbacks == []
    assert job.llm.generator.min_request_interval_seconds == 15.5

    expected = production.model_dump(exclude={"source_path"})
    expected["llm"]["fallbacks"] = []
    assert job.model_dump(exclude={"source_path"}) == expected
