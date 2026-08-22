"""One adapter for every endpoint that speaks the OpenAI chat shape.

Groq, NVIDIA NIM, SambaNova, Cerebras, OpenRouter, Together and a local
`mlx_lm.server` all accept the same `POST /chat/completions` body. Writing one
adapter for the shape rather than one class per company is what keeps a
provider disappearing a configuration change: an endpoint nobody has heard of
works today, given a base URL and the name of a variable holding its key.

The one place they genuinely differ is structured output. The same request that
returns clean JSON from one endpoint is rejected outright by the next, and a
third accepts the parameter and ignores it. So this asks for the strictest mode
first and steps down — a real schema, then bare JSON mode, then an instruction
in the prompt — remembering per instance which modes the endpoint has already
refused, so a run pays for that discovery once. The mode that produced the text
travels back on the `Completion`, because "this came from a model that was only
asked nicely for JSON" is worth knowing when a response fails to validate.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..config import ProviderConfig
from ..errors import ConfigError, ProviderError
from .base import (
    Completion,
    Message,
    RequestPacer,
    as_openai_messages,
    build_client,
    describe_response,
    is_shape_rejection,
    resolve_api_key,
    status_error,
    transport_error,
    with_json_instruction,
)

# How structured output was asked for. These strings end up in run logs, so
# they are named for what the operator would want to read.
SCHEMA_MODE_NONE = "none"
SCHEMA_MODE_STRICT = "json_schema"
SCHEMA_MODE_OBJECT = "json_object"
SCHEMA_MODE_PROMPT = "prompt"

# In preference order. Each is weaker than the one before and works on more
# endpoints than the one before.
_SCHEMA_MODES = (SCHEMA_MODE_STRICT, SCHEMA_MODE_OBJECT, SCHEMA_MODE_PROMPT)

@dataclass(frozen=True, slots=True)
class KnownEndpoint:
    """A base URL and key variable an operator would otherwise have to look up."""

    base_url: str
    api_key_env: str


# A convenience only. Nothing here is required: `ProviderConfig.base_url` and
# `ProviderConfig.api_key_env` override any of it, and a provider that is not
# listed works exactly as well once the job file supplies those two fields.
# Entries going stale is expected and costs nothing, because the job file has
# the last word.
KNOWN_ENDPOINTS: dict[str, KnownEndpoint] = {
    "groq": KnownEndpoint("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "mistral": KnownEndpoint("https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "nvidia": KnownEndpoint("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY"),
    "sambanova": KnownEndpoint("https://api.sambanova.ai/v1", "SAMBANOVA_API_KEY"),
    "cerebras": KnownEndpoint("https://api.cerebras.ai/v1", "CEREBRAS_API_KEY"),
    "openrouter": KnownEndpoint("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "together": KnownEndpoint("https://api.together.xyz/v1", "TOGETHER_API_KEY"),
    "openai": KnownEndpoint("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "deepinfra": KnownEndpoint(
        "https://api.deepinfra.com/v1/openai", "DEEPINFRA_API_KEY"
    ),
    "fireworks": KnownEndpoint(
        "https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY"
    ),
}


class OpenAICompatibleProvider:
    """A chat endpoint that accepts the OpenAI request body."""

    # The key under `usage` holding this provider's own meter, if it has one.
    # Subclasses set it; nothing here assumes tokens are the only unit anyone
    # charges in.
    usage_units_key: str | None = None

    def __init__(
        self,
        config: ProviderConfig,
        *,
        client: httpx.Client | None = None,
        require_api_key: bool = True,
        default_base_url: str | None = None,
        pacer: RequestPacer | None = None,
    ) -> None:
        self.name = config.provider
        self.model = config.model
        self._config = config

        known = KNOWN_ENDPOINTS.get(config.provider.strip().lower())
        base_url = config.base_url or (known.base_url if known else default_base_url)
        if not base_url:
            raise ConfigError(
                f"Provider {config.provider!r} is not one this engine has a base "
                "URL for. Add `base_url:` to it in the job file — any endpoint "
                "serving /chat/completions will work."
            )
        self.base_url = base_url.rstrip("/")

        self.api_key_env = config.api_key_env or (known.api_key_env if known else None)
        self._api_key = resolve_api_key(
            provider=config.provider,
            configured_env=self.api_key_env,
            required=require_api_key,
        )

        # An injected client is how tests reach this class without a network,
        # and it is also how two providers on one endpoint share a connection.
        self._client = client if client is not None else build_client(
            config.timeout_seconds
        )
        self._owns_client = client is None
        self._pacer = pacer or RequestPacer(config.min_request_interval_seconds)
        self.rate_limit_headers: dict[str, str] = {}

        # Modes this endpoint has already rejected. Kept per instance rather
        # than per class: the same provider name can point at two endpoints.
        self._rejected: set[str] = set()

    @property
    def label(self) -> str:
        return f"{self.name}/{self.model}"

    def complete(
        self,
        messages: list[Message],
        *,
        json_schema: dict | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> Completion:
        modes = self._modes(json_schema)
        for position, mode in enumerate(modes):
            is_last = position == len(modes) - 1
            payload = self._payload(
                messages,
                json_schema=json_schema,
                mode=mode,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
            try:
                data = self._post(payload)
            except ProviderError as error:
                if is_last or not is_shape_rejection(error):
                    raise
                # The endpoint understood the request enough to refuse its
                # shape. Ask for the same thing less ambitiously.
                self._rejected.add(mode)
                continue
            return self._completion(data, mode)

        # Unreachable: the loop above always returns or raises on its last pass.
        raise ProviderError(
            f"{self.name} was asked for a completion and produced none.",
            provider=self.name,
            retryable=True,
        )

    def close(self) -> None:
        """Release the connection pool, if this instance opened one."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OpenAICompatibleProvider:
        return self

    def __exit__(self, *exception: object) -> None:
        self.close()

    def _modes(self, json_schema: dict | None) -> list[str]:
        if json_schema is None:
            return [SCHEMA_MODE_NONE]
        remaining = [mode for mode in _SCHEMA_MODES if mode not in self._rejected]
        # Prompting for JSON needs no endpoint support at all, so it is always
        # available as a last resort even once everything else has been refused.
        return remaining or [SCHEMA_MODE_PROMPT]

    def _payload(
        self,
        messages: list[Message],
        *,
        json_schema: dict | None,
        mode: str,
        temperature: float | None,
        max_output_tokens: int | None,
    ) -> dict:
        prompt = list(messages)
        if mode in {SCHEMA_MODE_OBJECT, SCHEMA_MODE_PROMPT}:
            # JSON mode with no schema tells the endpoint the answer is JSON but
            # not what shape, and several endpoints additionally require the
            # word JSON in the prompt before they will enable it at all.
            prompt = with_json_instruction(prompt, json_schema)

        body: dict = {
            "model": self.model,
            "messages": as_openai_messages(prompt),
            "temperature": (
                self._config.temperature if temperature is None else temperature
            ),
            # `max_tokens` and not `max_completion_tokens`: the newer name is
            # unknown to several of the free endpoints, while every one of them
            # still accepts this one.
            "max_tokens": (
                self._config.max_output_tokens
                if max_output_tokens is None
                else max_output_tokens
            ),
            "stream": False,
        }

        if mode == SCHEMA_MODE_STRICT and json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": json_schema,
                },
            }
        elif mode == SCHEMA_MODE_OBJECT:
            body["response_format"] = {"type": "json_object"}

        return body

    def _post(self, payload: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        self._pacer.wait_for_slot()
        try:
            response = self._client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=headers
            )
        except httpx.HTTPError as cause:
            raise transport_error(self.name, cause) from cause

        self.rate_limit_headers = _rate_limit_headers(response.headers)

        if response.status_code >= 400:
            raise status_error(self.name, response, hint=self._hint(response))

        try:
            data = response.json()
        except ValueError as cause:
            raise self._body_error(
                response,
                f"answered with something that is not JSON: "
                f"{describe_response(response)}",
            ) from cause

        if not isinstance(data, dict):
            raise self._body_error(response, "answered with JSON that is not an object")
        return data

    def _completion(self, data: dict, mode: str) -> Completion:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError(
                f"{self.name} returned no choices for {self.model}.",
                provider=self.name,
                retryable=True,
            )

        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first.get("message"), dict) else {}
        text = _content_text(message.get("content"))

        if not text.strip():
            reason = first.get("finish_reason")
            detail = (
                " The whole budget went on reasoning tokens; raise "
                "max_output_tokens or use a model that does not think aloud."
                if reason == "length"
                else ""
            )
            raise ProviderError(
                f"{self.name} returned an empty completion "
                f"(finish_reason={reason!r}).{detail}",
                provider=self.name,
                retryable=True,
            )

        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        served = data.get("model")
        return Completion(
            text=text,
            provider=self.name,
            # The id the endpoint says it served, when it says one: providers
            # alias model names, and provenance should record what answered
            # rather than what was asked for.
            model=served if isinstance(served, str) and served else self.model,
            prompt_tokens=_token_count(usage.get("prompt_tokens")),
            completion_tokens=_token_count(usage.get("completion_tokens")),
            schema_mode=mode,
            usage_units=_usage_units(usage, self.usage_units_key),
        )

    def _hint(self, response: httpx.Response) -> str | None:
        if response.status_code in {401, 403}:
            named = self.api_key_env or "the provider's API key variable"
            return f"That reads as a rejected key; check {named}."
        if response.status_code == 404:
            return (
                f"Check that {self.model!r} is still in this provider's "
                f"catalogue and that {self.base_url} is its current base URL."
            )
        if response.status_code == 429:
            return "That is this provider's rate or quota limit."
        return None

    def _body_error(self, response: httpx.Response, what: str) -> ProviderError:
        error = ProviderError(
            f"{self.name} {what}.", provider=self.name, retryable=True
        )
        error.status_code = response.status_code
        error.retry_after = None
        return error


def _content_text(content: object) -> str:
    """Read the message text, whether it arrived as a string or as parts.

    The OpenAI shape says a string; endpoints serving multimodal models often
    answer with a list of parts even for plain text, and dropping those would
    look exactly like an empty completion.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        return "".join(pieces)
    return ""


def _usage_units(usage: dict, key: str | None) -> float | None:
    """The provider's own meter for this call, when it reports one."""
    if key is None:
        return None
    value = usage.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _token_count(value: object) -> int | None:
    """Usage counts are advisory; a provider that omits them is not an error."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _rate_limit_headers(headers: httpx.Headers) -> dict[str, str]:
    """Keep useful provider limit telemetry and nothing secret-bearing."""
    return {
        key.lower(): value
        for key, value in headers.items()
        if key.lower() == "retry-after"
        or key.lower().startswith("x-ratelimit-")
        or key.lower().startswith("ratelimit-")
    }
