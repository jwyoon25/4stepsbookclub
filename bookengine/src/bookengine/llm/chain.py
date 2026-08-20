"""Trying providers in turn, so that no one endpoint can stop a run.

The zero-cost requirement means depending on endpoints that are free, and free
endpoints go down, run out of quota, and change their model lists without
telling anyone. A chain makes that ordinary: the first provider is tried, and
when it fails for a reason that waiting could fix it is tried again, and when it
fails for a reason that waiting could not, the next provider takes over.

The distinction between those two kinds of failure is the whole value here. A
429 means slow down. A 401 means the key is wrong, and retrying a wrong key
eight times with backoff wastes two minutes and tells the operator nothing. So
`ProviderChainError` lists what each provider actually said, because "all
providers failed" is not a sentence anyone can act on.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ..errors import ProviderChainError, ProviderError
from .base import Completion, LLMProvider, Message
from .cache import ResponseCache

# Backoff doubles from here. Free endpoints publish per-minute quotas, so the
# ceiling is high enough to outlast one.
BASE_DELAY_SECONDS = 2.0
MAX_DELAY_SECONDS = 45.0


@dataclass(slots=True)
class Attempt:
    """One provider's last word, kept for the failure message."""

    provider: str
    model: str
    error: str
    retryable: bool
    attempts: int


@dataclass(slots=True)
class ProviderChain:
    """An ordered set of endpoints that answer the same question."""

    providers: list[LLMProvider]
    max_attempts: int = 3
    cache: ResponseCache | None = None
    # Injected so tests exercise the backoff without waiting for it, and so a
    # future caller can make a run interruptible.
    sleep: Callable[[float], None] = time.sleep
    jitter: Callable[[], float] = random.random
    calls: int = field(default=0, init=False)
    cache_hits: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if not self.providers:
            raise ProviderChainError("A provider chain needs at least one provider.")

    @property
    def labels(self) -> list[str]:
        return [f"{provider.name}/{provider.model}" for provider in self.providers]

    @property
    def primary(self) -> LLMProvider:
        return self.providers[0]

    def complete(
        self,
        messages: list[Message],
        *,
        json_schema: dict | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> Completion:
        """Answer once, from whichever provider can.

        The cache is consulted per provider rather than per chain, because the
        answer belongs to the model that gave it. A cached run that then adds a
        fallback provider still replays from cache; one that reorders the chain
        correctly does not.
        """
        history: list[Attempt] = []

        for provider in self.providers:
            key = None
            if self.cache is not None:
                key = self.cache.key(
                    provider=provider.name,
                    model=provider.model,
                    messages=messages,
                    json_schema=json_schema,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                )
                hit = self.cache.load(key)
                if hit is not None:
                    self.cache_hits += 1
                    return hit

            attempt, last = 0, None
            while attempt < self.max_attempts:
                attempt += 1
                try:
                    self.calls += 1
                    completion = provider.complete(
                        messages,
                        json_schema=json_schema,
                        temperature=temperature,
                        max_output_tokens=max_output_tokens,
                    )
                except ProviderError as error:
                    last = error
                    if not error.retryable or attempt >= self.max_attempts:
                        break
                    self.sleep(self._delay(attempt, error))
                    continue

                if self.cache is not None and key is not None:
                    self.cache.store(key, completion)
                return completion

            history.append(
                Attempt(
                    provider=provider.name,
                    model=provider.model,
                    error=str(last) if last else "unknown failure",
                    retryable=bool(last and last.retryable),
                    attempts=attempt,
                )
            )

        failure = ProviderChainError(self._summary(history))
        # The attempts travel with the error as well as inside its message. A
        # caller that has to act differently for "slow down" than for "wrong
        # key" — the smoke test does — should not have to parse prose to find
        # out which one it was.
        failure.attempts = list(history)
        raise failure

    def _delay(self, attempt: int, error: ProviderError) -> float:
        """How long to wait before trying the same provider again.

        An endpoint that sent `Retry-After` has told us its answer, and it is
        better than a guess — but it is not allowed to park a run for an hour,
        so it is capped like any other delay.
        """
        advertised = getattr(error, "retry_after", None)
        if advertised is not None:
            return min(float(advertised), MAX_DELAY_SECONDS)
        backoff = min(BASE_DELAY_SECONDS * (2 ** (attempt - 1)), MAX_DELAY_SECONDS)
        # Jitter keeps several lessons in one run from retrying in lockstep.
        return backoff * (0.5 + 0.5 * self.jitter())

    @staticmethod
    def _summary(history: list[Attempt]) -> str:
        lines = ["Every configured provider failed for this call."]
        for record in history:
            waited = " after retrying" if record.attempts > 1 else ""
            lines.append(
                f"  - {record.provider}/{record.model}{waited} "
                f"({record.attempts} attempt(s)): {record.error}"
            )
        lines.append(
            "Check the quota and key for the first provider, or add another to "
            "`llm.fallbacks` in the job file."
        )
        return "\n".join(lines)

    def close(self) -> None:
        for provider in self.providers:
            closer = getattr(provider, "close", None)
            if callable(closer):
                closer()
