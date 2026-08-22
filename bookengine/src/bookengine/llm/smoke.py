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
    # What this endpoint is for: `generator`, `auditor`, `fallback`, or
    # `benchmark`. Carried so the report can say plainly that an evaluation
    # endpoint answered and is still not going to see a book.
    role: str = "generator"
    label_provider: str = ""
    api_key_env: str | None = None
    api_key_present: bool = False
    reached: bool = False
    parsed: bool = False
    answered_correctly: bool = False
    model_reported: str | None = None
    schema_mode: str | None = None
    seconds: float = 0.0
    usage_units: float | None = None
    retryable: bool | None = None
    error: str | None = None
    checks: dict[str, bool] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Whether this endpoint can be used for a run as it stands."""
        return self.reached and self.parsed and self.answered_correctly

    def render_block(self) -> str:
        """One endpoint, as a column an operator reads down.

        Each line is a stage of the same request, in the order they had to
        succeed, so a failure names the stage that stopped rather than leaving
        somebody to infer it from an HTTP code.
        """
        rows = [f"{self.label}   [{self.role}]"]

        def row(name: str, value: str) -> str:
            return f"  {name}{'.' * max(2, 24 - len(name))} {value}"

        if not self.api_key_present:
            rows.append(row("credential", f"MISSING  {self.error or ''}"))
            return "\n".join(rows)

        rows.append(row("credential", "PASS"))
        if not self.reached:
            label = {True: "RATE LIMITED / BUSY", False: "REFUSED"}.get(
                self.retryable, "UNREACHABLE"
            )
            rows.append(row("endpoint", f"{label}  {self.error or ''}"))
            return "\n".join(rows)

        rows.append(row("endpoint", f"PASS  {self.seconds:.1f}s"))
        rows.append(
            row("model", f"{self.model_reported}"
                + ("" if self.checks.get("model_id_matches_request", True)
                   else "   <- SUBSTITUTED, not what was asked for"))
        )
        if not self.parsed:
            rows.append(row("structured output", f"FAILED  {self.error or ''}"))
            return "\n".join(rows)

        rows.append(row("structured output", f"PASS  ({self.schema_mode})"))
        rows.append(
            row("answer", "PASS" if self.answered_correctly
                else "WRONG  right shape, wrong contents")
        )
        rows.append(row("provenance", "PASS" if self.checks.get(
            "reported_a_model_id") else "no model id returned"))
        if self.usage_units is not None:
            rows.append(row("usage", f"{self.usage_units:.1f} units"))
        if self.role == "benchmark":
            rows.append(row("routing", "benchmark only — never sees book text"))
        return "\n".join(rows)

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
            "role": self.role,
            "seconds": round(self.seconds, 2),
            "usage_units": self.usage_units,
            "retryable": self.retryable,
            "error": self.error,
            "checks": dict(self.checks),
        }


def smoke_test_provider(
    config: ProviderConfig, *, role: str = "generator", timer=time.monotonic
) -> SmokeResult:
    """Send one endpoint the smallest structured request there is.

    A chain of one, with retries turned off: a smoke test is asking whether the
    endpoint works now, and backing off for forty-five seconds to find out
    twice is the opposite of what it is for. That also makes the rate-limit
    case visible as itself — a 429 arrives as an unreachable endpoint marked
    retryable, rather than as a pause.
    """
    result = SmokeResult(
        label=config.label,
        role=role,
        label_provider=config.provider,
        api_key_env=config.api_key_env,
    )

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
    result.usage_units = completion.usage_units
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
    """Test every endpoint a job names, in the order a run would reach them.

    The generator and the auditor first, then the shared fallbacks, because a
    run whose primaries are fine never touches the rest and a run whose
    primaries are down depends entirely on them. Benchmark endpoints come last
    and are labelled as such: they are tested because a key is configured and
    somebody will want to know it still works, not because a workbook will ever
    reach one.
    """
    seen: set[str] = set()
    results: list[SmokeResult] = []

    roles = [
        (config.generator, "generator"),
        (config.auditor, "auditor"),
        *((provider, "fallback") for provider in config.fallbacks),
        *((provider, "benchmark") for provider in config.benchmark),
    ]
    for provider, role in roles:
        if provider.label in seen:
            continue
        seen.add(provider.label)
        results.append(smoke_test_provider(provider, role=role))

    return results


def render_report(results: list[SmokeResult], config: LLMConfig) -> str:
    """What the results mean for a run, given this job's audit policy.

    The per-endpoint blocks are `SmokeResult.render_block`; this is the reading
    of them. It ends with the route a workbook would actually take, because
    that — not the list of endpoints that happened to answer — is the thing an
    operator is deciding whether to trust.
    """
    lines: list[str] = []
    by_role = {result.label: result for result in results}
    routable = [
        result for result in results
        if result.role != "benchmark" and result.ok
    ]

    if not routable:
        lines.append(
            "No endpoint a workbook could use answered. A run would fail at "
            "its first model call."
        )
        return "\n".join(lines)

    generator = by_role.get(config.generator.label)
    auditor = by_role.get(config.auditor.label)
    def state(label: str) -> str:
        """How a chain would fare with this endpoint, not just whether it
        answered once. Retries are off during a smoke test, so an endpoint that
        is merely busy looks identical to one that is refusing — and a run
        would tell them apart, because the chain retries one and not the other.
        """
        result = by_role.get(label)
        if result is None:
            return "untested"
        if result.ok:
            return "ready"
        return "busy" if result.retryable else "down"

    working_fallbacks = [
        provider.label for provider in config.fallbacks
        if state(provider.label) in {"ready", "busy"}
    ]

    def route(name: str, configured, result) -> str:
        if result is not None and result.ok:
            return f"  {name}{'.' * max(2, 24 - len(name))} {configured.label}"
        first = next(
            (label for label in working_fallbacks if label != configured.label),
            None,
        )
        state = f"{configured.label} DOWN"
        return (
            f"  {name}{'.' * max(2, 24 - len(name))} {state}"
            + (f" -> {first}" if first else " -> nothing left")
        )

    lines.append("Production route")
    lines.append(route("generator", config.generator, generator))
    lines.append(route("auditor", config.auditor, auditor))
    lines.append(
        f"  {'fallback'}{'.' * 16} "
        + (
            ", ".join(
                f"{label} ({state(label)})" for label in working_fallbacks
            )
            if working_fallbacks
            else "none reachable"
        )
    )

    benchmarks = [result.label for result in results if result.role == "benchmark"]
    if benchmarks:
        lines.append(f"  {'benchmark only'}{'.' * 10} {', '.join(benchmarks)}")

    # What independence the reachable endpoints can actually deliver today.
    providers = {
        result.label_provider
        for result in results
        if result.role != "benchmark" and state(result.label) in {"ready", "busy"}
    }
    requirement = config.audit.requirement
    if len(providers) >= 2:
        lines.append(f"  {'independence'}{'.' * 12} provider (requirement: "
                     f"{requirement})")
    else:
        lines.append(
            f"  {'independence'}{'.' * 12} NONE — one provider reachable, and "
            f"`llm.audit.requirement` is `{requirement}`. Every row would be "
            f"written and audited by the same endpoint, and `on_shared` is "
            f"`{config.audit.on_shared}`, so none would export as proved."
        )

    substituted = [
        result for result in routable
        if not result.checks.get("model_id_matches_request", True)
    ]
    for result in substituted:
        lines.append(
            f"\n{result.label} answered as {result.model_reported}. The "
            "provider substituted a model; provenance records what answered."
        )

    return "\n".join(lines)


def _first_line(message: str) -> str:
    """One line of an error, so a table stays a table."""
    return message.strip().splitlines()[0][:160]
