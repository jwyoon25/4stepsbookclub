"""Finding out whether an endpoint works before spending a book on it.

Every provider adapter in this package was written against documentation and
tested against a fake. That is enough to know the parsing is right and nothing
about whether the endpoint answers, whether it honours a JSON schema, what it
does at its rate limit, or whether the model id in the job file still exists —
and a free provider's answer to all four changes without notice.

So this is the smallest real call that exercises the whole path: authenticate,
send a schema, get a shape back, and report which of those actually happened.
It is deliberately tiny. A run that fails at the first audit batch has already
cost an ingestion and a hundred generation calls; this costs one request per
endpoint and tells you the same thing.

Nothing here prints a key or puts one in a result. The report says which
environment variable an endpoint reads and whether it was set, which is what
somebody debugging needs, and never the value.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from pydantic import Field

from ..config import LLMConfig, ProviderConfig
from ..errors import (
    BookEngineError,
    ConfigError,
    ProviderChainError,
    ProviderError,
    StructuredResponseError,
)
from ..vocabulary.schemas import _Answer
from .base import Message
from .chain import ProviderChain
from .registry import build_provider
from .structured import generate_structured


class SmokeAnswer(_Answer):
    """The shape a smoke test asks for.

    Chosen so that a wrong answer is obvious: a fixed string the model is told
    to copy, and a number it has to read out of the prompt. An endpoint that
    returns valid JSON with the wrong contents is answering from somewhere
    other than the prompt, which is worth knowing before it writes definitions.
    """

    echo: str = Field(
        min_length=1,
        max_length=40,
        description="Copy the word given in the message, exactly, in lowercase.",
    )
    total: int = Field(
        ge=0,
        le=1000,
        description="The sum of the two numbers given in the message.",
    )


# The prompt, with its own answer known. Kept short: the point is to reach the
# endpoint, not to measure it.
SMOKE_WORD = "verified"
SMOKE_ADDENDS = (17, 25)
SMOKE_TOTAL = sum(SMOKE_ADDENDS)

SMOKE_SYSTEM = (
    "You answer only with the JSON object you were asked for. No preamble, no "
    "commentary, no code fence."
)
SMOKE_USER = (
    f"The word is {SMOKE_WORD!r}. The two numbers are {SMOKE_ADDENDS[0]} and "
    f"{SMOKE_ADDENDS[1]}.\n\n"
    'Return one JSON object: {"echo": "<the word, lowercase>", '
    '"total": <the two numbers added together>}'
)


@dataclass(slots=True)
class SmokeResult:
    """What one endpoint did when it was asked the smallest possible question."""

    label: str
    api_key_env: str | None = None
    api_key_present: bool = False
    reached: bool = False
    parsed: bool = False
    answered_correctly: bool = False
    model_reported: str | None = None
    schema_mode: str | None = None
    seconds: float = 0.0
    retryable: bool | None = None
    error: str | None = None
    checks: dict[str, bool] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Whether this endpoint can be used for a run as it stands."""
        return self.reached and self.parsed and self.answered_correctly

    def render(self) -> str:
        if self.ok:
            detail = (
                f"OK  {self.seconds:.1f}s  model={self.model_reported} "
                f"schema={self.schema_mode}"
            )
        elif not self.api_key_present:
            detail = f"NOT CONFIGURED  {self.error}"
        elif not self.reached:
            label = {True: "RATE LIMITED / BUSY", False: "REFUSED"}.get(
                self.retryable, "UNREACHABLE"
            )
            detail = f"{label}  {self.error}"
        elif not self.parsed:
            detail = f"BAD SHAPE  {self.error}"
        else:
            detail = (
                "WRONG ANSWER  the endpoint returned the right shape with the "
                "wrong contents, so it is not reading the prompt"
            )
        return f"{self.label:<44} {detail}"

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            # The variable's name, never its value.
            "api_key_env": self.api_key_env,
            "api_key_present": self.api_key_present,
            "reached": self.reached,
            "parsed": self.parsed,
            "answered_correctly": self.answered_correctly,
            "model_reported": self.model_reported,
            "schema_mode": self.schema_mode,
            "seconds": round(self.seconds, 2),
            "retryable": self.retryable,
            "error": self.error,
            "checks": dict(self.checks),
        }


def smoke_test_provider(
    config: ProviderConfig, *, timer=time.monotonic
) -> SmokeResult:
    """Send one endpoint the smallest structured request there is.

    A chain of one, with retries turned off: a smoke test is asking whether the
    endpoint works now, and backing off for forty-five seconds to find out
    twice is the opposite of what it is for. That also makes the rate-limit
    case visible as itself — a 429 arrives as an unreachable endpoint marked
    retryable, rather than as a pause.
    """
    result = SmokeResult(label=config.label, api_key_env=config.api_key_env)

    started = timer()
    try:
        endpoint = build_provider(config)
    except ConfigError as failure:
        # The adapter names the variable it wanted, which is the whole content
        # of this case. Building it is also the only place that knows which
        # variable that is, so nothing here keeps a second copy of the table.
        result.error = _first_line(str(failure))
        result.seconds = timer() - started
        return result

    # Construction succeeded, so either a key was found or the endpoint needs
    # none. The variable's name is reported; its value is never read here.
    result.api_key_env = getattr(endpoint, "api_key_env", None) or config.api_key_env
    result.api_key_present = True
    chain = ProviderChain(providers=[endpoint], max_attempts=1)

    try:
        answer, completion = generate_structured(
            chain,
            [
                Message(role="system", content=SMOKE_SYSTEM),
                Message(role="user", content=SMOKE_USER),
            ],
            SmokeAnswer,
            max_repairs=0,
        )
    except StructuredResponseError as failure:
        # The endpoint answered; what came back was not the requested shape.
        result.reached = True
        result.error = _first_line(str(failure))
        result.seconds = timer() - started
        return result
    except ProviderChainError as failure:
        # One endpoint, so there is exactly one attempt to report — and what it
        # said is the whole answer here. A 429 and a 401 both stop a run, but
        # only one of them is worth waiting out.
        last = failure.attempts[-1] if failure.attempts else None
        result.error = _first_line(last.error if last else str(failure))
        result.retryable = last.retryable if last else None
        result.seconds = timer() - started
        return result
    except ProviderError as failure:
        result.error = _first_line(str(failure))
        result.retryable = failure.retryable
        result.seconds = timer() - started
        return result
    except BookEngineError as failure:
        result.error = _first_line(str(failure))
        result.seconds = timer() - started
        return result
    finally:
        chain.close()

    result.seconds = timer() - started
    result.reached = True
    result.parsed = True
    result.model_reported = completion.model
    result.schema_mode = completion.schema_mode
    result.checks = {
        "authenticated": True,
        "structured_response_parsed": True,
        "echoed_the_prompt": answer.echo.strip().lower() == SMOKE_WORD,
        "did_the_arithmetic": answer.total == SMOKE_TOTAL,
        "reported_a_model_id": bool(completion.model),
        # A completion whose model id is not the one that was asked for means
        # the provider silently substituted, which the run's provenance would
        # otherwise record without anybody noticing.
        "model_id_matches_request": completion.model == config.model,
    }
    result.answered_correctly = (
        result.checks["echoed_the_prompt"] and result.checks["did_the_arithmetic"]
    )
    return result


def smoke_test_all(config: LLMConfig) -> list[SmokeResult]:
    """Test every endpoint a job could reach, in the order a run would try them.

    The generator and the auditor first, then the shared fallbacks, because a
    run whose primaries are fine never touches the rest and a run whose
    primaries are down depends entirely on them.
    """
    seen: set[str] = set()
    results: list[SmokeResult] = []

    for provider in (config.generator, config.auditor, *config.fallbacks):
        if provider.label in seen:
            continue
        seen.add(provider.label)
        results.append(smoke_test_provider(provider))

    return results


def render_report(results: list[SmokeResult], config: LLMConfig) -> str:
    """What the results mean for a run, given this job's audit policy.

    The per-endpoint lines are `SmokeResult.render`; this is only the reading
    of them, because the two are printed together and saying it twice would
    make the important half harder to find.
    """
    lines: list[str] = []
    working = [result for result in results if result.ok]

    if not working:
        lines.append(
            "No endpoint answered. A run would fail at its first model call."
        )
        return "\n".join(lines)

    providers = {result.label.split("/", 1)[0] for result in working}
    lines.append(
        f"{len(working)} of {len(results)} endpoint(s) answered, across "
        f"{len(providers)} provider(s)."
    )

    if len(providers) < 2 and config.audit.requirement == "provider":
        lines.append(
            "Only one provider is reachable, and `llm.audit.requirement` is "
            "`provider`. Every row would be written and audited by the same "
            f"endpoint, and `llm.audit.on_shared` is `{config.audit.on_shared}`."
        )

    substituted = [
        result
        for result in working
        if not result.checks.get("model_id_matches_request", True)
    ]
    for result in substituted:
        lines.append(
            f"{result.label} answered as {result.model_reported}. The provider "
            "substituted a model; provenance will record what answered."
        )

    return "\n".join(lines)


def _first_line(message: str) -> str:
    """One line of an error, so a table stays a table."""
    return message.strip().splitlines()[0][:160]
