"""The one shape a model call has, whatever endpoint answers it.

Zero marginal inference cost is a product requirement, so the engine runs on
whichever endpoints are free this month. Those endpoints appear, rename their
models, tighten their quotas and vanish without notice. Nothing above this
package is therefore allowed to know a provider's name: the pipeline asks for a
completion, and which company answers it is a line in a job file.

That is what these types buy. `Message` and `Completion` are the whole
vocabulary the rest of the engine needs, and `LLMProvider` is the whole contract
an adapter has to meet, so supporting a new endpoint is a new file in this
package and no change anywhere else.

Calls are synchronous. The pipeline spends its time parsing PDFs and matching
strings rather than waiting on sockets, and a synchronous call site reads like
the step it is instead of like plumbing.

Two conventions shared by every adapter here are defined in this module. The
first is `ProviderError.retryable`, which is what the chain reads to choose
between waiting and moving on: a quota is worth waiting for, a rejected key
never is. The second is that the helpers below attach `status_code` and
`retry_after` to the errors they build, rather than those becoming constructor
arguments, because HTTP vocabulary has no business in an exception hierarchy
shared with the PDF layer. A `status_code` of `None` means the request never
reached the server at all, which is the difference between "this provider said
no" and "this provider is not there".
"""

from __future__ import annotations

import email.utils
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol

import httpx

from ..errors import ConfigError, ProviderError

# The three roles every chat endpoint in use understands. Anything else is a
# typo at the call site, and a silently ignored role would quietly drop a whole
# instruction from a prompt.
ROLES = frozenset({"system", "user", "assistant"})

# Statuses worth trying the same endpoint again for. Everything else is the
# operator's problem — a rejected key, a model id the provider has retired —
# and repeating the call only spends the attempt budget before the chain moves
# on to a provider that might work.
RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 529})

# Statuses that mean "I understood the call, but not the way you asked for
# structured output". Free endpoints advertise more JSON support than they have,
# and this is how the disagreement arrives.
SHAPE_REJECTION_STATUS = frozenset({400, 415, 422, 501})

# Free endpoints answer failures with anything from a JSON error object to a
# gateway's HTML. Enough of it to diagnose the problem, not enough to fill a log.
_BODY_CHARACTERS = 300


@dataclass(frozen=True, slots=True)
class Message:
    """One turn of a prompt."""

    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(
                f"{self.role!r} is not a message role; expected one of "
                + ", ".join(sorted(ROLES))
                + "."
            )


@dataclass(frozen=True, slots=True)
class Completion:
    """What came back, and who it came from.

    The provider and model travel with the text because they end up in an
    item's provenance: an operator asking "which model wrote this definition"
    is asking about one workbook row, months later.

    `schema_mode` records how structured output was actually requested. Free
    endpoints advertise more JSON support than they have, so an adapter may have
    had to fall back from a real schema to a bare JSON mode to a plain
    instruction, and a run's log should say which of those produced this text.
    """

    text: str
    provider: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    cached: bool = False
    schema_mode: str | None = None


class LLMProvider(Protocol):
    """One endpoint that can answer a prompt.

    Deliberately one method. Anything richer — streaming, tools, embeddings —
    would be a capability the chain has to reason about, and a chain whose links
    are not interchangeable cannot fall back.
    """

    name: str
    model: str

    def complete(
        self,
        messages: list[Message],
        *,
        json_schema: dict | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> Completion: ...


def build_client(
    timeout_seconds: float, headers: Mapping[str, str] | None = None
) -> httpx.Client:
    """One HTTP client per endpoint, carrying that endpoint's timeout.

    The timeout is the provider's own setting rather than a global, because a
    local model on a laptop and a hosted endpoint behind a queue are slow for
    different reasons and deserve different patience.
    """
    return httpx.Client(timeout=timeout_seconds, headers=dict(headers or {}))


def resolve_api_key(
    *,
    provider: str,
    configured_env: str | None,
    fallback_envs: Sequence[str] = (),
    required: bool = True,
) -> str:
    """Read a key from the environment, naming the variable when it is missing.

    Keys never appear in a job file — a job file is committed and a key is not —
    so the only question this can answer badly is "which variable did you want
    me to read". It therefore names it. When the job sets `api_key_env`, that
    name is the only one tried: falling back to a provider default would hide
    the operator's own typo.
    """
    names = [configured_env] if configured_env else list(fallback_envs)
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value

    if not required:
        return ""
    if not names:
        raise ConfigError(
            f"No API key variable is known for provider {provider!r}. Add "
            "`api_key_env: THE_VARIABLE_NAME` to that provider in the job file."
        )
    listed = " or ".join(names)
    raise ConfigError(
        f"{provider} needs an API key but {listed} is not set in the "
        f"environment. Export it, for example `export {names[0]}=...`."
    )


def split_system(messages: Sequence[Message]) -> tuple[str | None, list[Message]]:
    """Separate system instructions from the conversation.

    Endpoints outside the OpenAI shape carry the system prompt in its own field
    rather than as a turn. Several system messages are joined in order, so a
    caller that builds its instructions in pieces keeps them.
    """
    system = [message.content for message in messages if message.role == "system"]
    rest = [message for message in messages if message.role != "system"]
    return ("\n\n".join(system) if system else None), rest


def as_openai_messages(messages: Sequence[Message]) -> list[dict[str, str]]:
    """The wire form used by every OpenAI-compatible endpoint."""
    return [{"role": message.role, "content": message.content} for message in messages]


def json_instruction(schema: dict | None) -> str:
    """The prompt-only way of asking for JSON, for endpoints with no other way.

    This is the weakest of the structured-output modes and is written to be
    blunt, because the models that need it are the ones most inclined to
    introduce their answer first.
    """
    opening = (
        "Reply with JSON only. Do not wrap it in a code fence, and write no "
        "prose before or after it."
    )
    if not schema:
        return opening
    rendered = json.dumps(schema, ensure_ascii=False, sort_keys=True)
    return f"{opening} The JSON must match this JSON Schema exactly:\n{rendered}"


def with_json_instruction(
    messages: Sequence[Message], schema: dict | None
) -> list[Message]:
    """Append the JSON instruction to the last user turn.

    Appended rather than added as a new turn: some endpoints reject two user
    turns in a row, and the instruction is about the answer being asked for, so
    it belongs with the question.
    """
    instruction = json_instruction(schema)
    updated = list(messages)
    for index in range(len(updated) - 1, -1, -1):
        if updated[index].role == "user":
            joined = f"{updated[index].content}\n\n{instruction}"
            updated[index] = replace(updated[index], content=joined)
            return updated
    updated.append(Message(role="user", content=instruction))
    return updated


def describe_response(response: httpx.Response) -> str:
    """The most useful sentence available from a failed response.

    Providers bury the real reason in `error.message`, in `detail`, or nowhere
    at all. Quota exhaustion and an unknown model id look identical at the
    status line and completely different one level in, and the operator needs
    the level in.
    """
    payload: object = None
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        error = payload.get("error")
        candidate: object = None
        if isinstance(error, dict):
            candidate = error.get("message") or error.get("code") or error.get("status")
        elif isinstance(error, str):
            candidate = error
        if not candidate:
            candidate = payload.get("message") or payload.get("detail")
        if isinstance(candidate, str) and candidate.strip():
            return _condense(candidate)

    return _condense(response.text or "")


def retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    """How long the provider asked to be left alone, in seconds.

    `Retry-After` comes as either a count of seconds or an HTTP date, and free
    tiers use both. Honouring it is the difference between a chain that backs
    off politely and one that spends its remaining quota discovering it has
    none.
    """
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if not raw:
        return None
    raw = raw.strip()

    try:
        return max(0.0, float(raw))
    except ValueError:
        pass

    try:
        when = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def status_error(
    provider: str, response: httpx.Response, *, hint: str | None = None
) -> ProviderError:
    """Turn a failed HTTP response into an error the chain can act on."""
    retryable = response.status_code in RETRYABLE_STATUS
    detail = describe_response(response)
    text = f"{provider} returned HTTP {response.status_code}"
    if detail:
        text = f"{text}: {detail}"
    # A hint explains what the operator should change, so it is only worth
    # printing when waiting will not fix it by itself.
    if hint and not retryable:
        text = f"{text}. {hint}"

    error = ProviderError(text, provider=provider, retryable=retryable)
    error.status_code = response.status_code
    error.retry_after = retry_after_seconds(response.headers)
    return error


def transport_error(provider: str, cause: Exception) -> ProviderError:
    """Turn a failure to reach the endpoint into an error the chain can act on.

    Timeouts and dropped connections are the ordinary weather of free endpoints
    and are worth another attempt. A bad URL or an unknown scheme is a job file
    that needs editing, and no amount of waiting edits it.
    """
    retryable = isinstance(
        cause,
        httpx.TimeoutException | httpx.NetworkError | httpx.RemoteProtocolError,
    )
    error = ProviderError(
        f"{provider} could not be reached: {type(cause).__name__}: {cause}",
        provider=provider,
        retryable=retryable,
    )
    error.status_code = None
    error.retry_after = None
    return error


def is_shape_rejection(error: ProviderError) -> bool:
    """Whether the endpoint refused the request's shape rather than the request.

    These are the statuses an endpoint answers with when it has never heard of
    the way structured output was asked for. It is a reason to ask again more
    simply, not a reason to give up on the provider, and it is the same
    judgement for every adapter here, so it is made once.
    """
    return getattr(error, "status_code", None) in SHAPE_REJECTION_STATUS


def reached_server(error: ProviderError) -> bool:
    """Whether the request got as far as an answer.

    A provider that answered with a refusal and a provider that is not running
    call for opposite advice, and only the adapter that raised the error knows
    which it was, so it says so on the error.
    """
    return getattr(error, "status_code", None) is not None


def _condense(value: str) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= _BODY_CHARACTERS:
        return collapsed
    return collapsed[:_BODY_CHARACTERS].rstrip() + "..."
