"""Google's generative language endpoint, which is not the OpenAI shape.

Gemini's free tier is one of the few endpoints that will still be there next
month, so it is worth an adapter of its own even though it means a second
request format. Three things differ enough to matter: the system prompt is its
own field rather than a turn, the assistant is called `model`, and structured
output is requested with a schema that only looks like JSON Schema.

That last one is the reason most of this file exists. Gemini accepts a
restricted subset — an enum of type names, a short allow-list of keywords, no
`$ref`, no `additionalProperties` — and answers anything else with a 400 that
names one offending keyword at a time. Sending a pydantic model's schema
unedited would fail on almost every model in this engine, so schemas are
translated here, and a schema that cannot be translated honestly makes the
adapter fall back to asking for JSON without one rather than pretend.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from ..config import ProviderConfig
from ..errors import ProviderError
from .base import (
    Completion,
    Message,
    RequestPacer,
    build_client,
    describe_response,
    is_shape_rejection,
    json_instruction,
    resolve_api_key,
    split_system,
    status_error,
    transport_error,
    with_json_instruction,
)
from .openai_compatible import (
    SCHEMA_MODE_NONE,
    SCHEMA_MODE_OBJECT,
    SCHEMA_MODE_PROMPT,
    SCHEMA_MODE_STRICT,
)

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# GOOGLE_API_KEY is the older name and still what many machines have set.
API_KEY_ENVIRONMENT = ("GEMINI_API_KEY", "GOOGLE_API_KEY")

# The keywords Gemini's schema dialect understands. Everything else — `$schema`,
# `$defs`, `title`, `default`, `additionalProperties`, `exclusiveMinimum` and the
# rest of JSON Schema — is rejected rather than ignored, so it is dropped here.
_SUPPORTED_KEYWORDS = frozenset(
    {
        "type",
        "format",
        "description",
        "nullable",
        "enum",
        "items",
        "properties",
        "required",
        "propertyOrdering",
        "anyOf",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
    }
)

# Gemini's `type` is a protobuf enum, so it wants the enum's own spelling.
_TYPE_NAMES = {
    "string": "STRING",
    "number": "NUMBER",
    "integer": "INTEGER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
    "object": "OBJECT",
}

# `format` is only honoured for these, and rejected outright for the ones
# pydantic likes to emit, such as `email` or `uuid`.
_SUPPORTED_FORMATS = frozenset(
    {"float", "double", "int32", "int64", "enum", "date-time"}
)

# Deep enough for any schema this engine sends, shallow enough that a
# self-referencing model is caught rather than expanded until memory runs out.
_MAX_SCHEMA_DEPTH = 12


class UntranslatableSchema(Exception):
    """This schema has no honest equivalent in Gemini's dialect.

    Internal to this module: it is caught here and turned into asking for JSON
    without a schema, which is a weaker request but a truthful one.
    """


@dataclass(frozen=True, slots=True)
class _Reply:
    """The parts of a `generateContent` response this adapter uses."""

    text: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None


class GeminiProvider:
    """Google's `:generateContent` endpoint, behind the same one method."""

    def __init__(
        self,
        config: ProviderConfig,
        *,
        client: httpx.Client | None = None,
        pacer: RequestPacer | None = None,
    ) -> None:
        self.name = config.provider
        # `models/gemini-x` and `gemini-x` are both things people write down.
        self.model = config.model.removeprefix("models/")
        self._config = config
        self.base_url = (config.base_url or DEFAULT_BASE_URL).rstrip("/")

        self.api_key_env = config.api_key_env or API_KEY_ENVIRONMENT[0]
        self._api_key = resolve_api_key(
            provider=config.provider,
            configured_env=config.api_key_env,
            fallback_envs=API_KEY_ENVIRONMENT,
        )

        self._client = client if client is not None else build_client(
            config.timeout_seconds
        )
        self._owns_client = client is None
        self._pacer = pacer or RequestPacer(config.min_request_interval_seconds)
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
                self._rejected.add(mode)
                continue
            reply = self._read(data)
            return Completion(
                text=reply.text,
                provider=self.name,
                model=reply.model,
                prompt_tokens=reply.prompt_tokens,
                completion_tokens=reply.completion_tokens,
                schema_mode=mode,
            )

        # Unreachable: the last pass of the loop always returns or raises.
        raise ProviderError(
            f"{self.name} was asked for a completion and produced none.",
            provider=self.name,
            retryable=True,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> GeminiProvider:
        return self

    def __exit__(self, *exception: object) -> None:
        self.close()

    def _modes(self, json_schema: dict | None) -> list[str]:
        if json_schema is None:
            return [SCHEMA_MODE_NONE]
        wanted = (SCHEMA_MODE_STRICT, SCHEMA_MODE_OBJECT, SCHEMA_MODE_PROMPT)
        remaining = [mode for mode in wanted if mode not in self._rejected]
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
            prompt = with_json_instruction(prompt, json_schema)

        system, conversation = split_system(prompt)
        generation: dict = {
            "temperature": (
                self._config.temperature if temperature is None else temperature
            ),
            "maxOutputTokens": (
                self._config.max_output_tokens
                if max_output_tokens is None
                else max_output_tokens
            ),
        }

        if mode == SCHEMA_MODE_STRICT and json_schema is not None:
            try:
                generation["responseSchema"] = sanitise_schema(json_schema)
            except UntranslatableSchema:
                # Nothing is gained by sending a schema Gemini will refuse, and
                # the JSON mime type alone still constrains the answer usefully.
                self._rejected.add(SCHEMA_MODE_STRICT)
                generation.pop("responseSchema", None)
                mode = SCHEMA_MODE_OBJECT
                prompt = with_json_instruction(list(messages), json_schema)
                system, conversation = split_system(prompt)
            generation["responseMimeType"] = "application/json"
        elif mode == SCHEMA_MODE_OBJECT:
            generation["responseMimeType"] = "application/json"

        payload: dict = {
            "contents": [
                {
                    # Gemini calls the assistant "model"; there is no third role.
                    "role": "model" if message.role == "assistant" else "user",
                    "parts": [{"text": message.content}],
                }
                for message in conversation
            ],
            "generationConfig": generation,
        }
        if system:
            # Both `system_instruction` and `systemInstruction` are accepted;
            # the underscored spelling is the one the API reference documents.
            payload["system_instruction"] = {"parts": [{"text": system}]}
        return payload

    def _post(self, payload: dict) -> dict:
        url = f"{self.base_url}/models/{self.model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            # In a header rather than the `?key=` query parameter the quickstart
            # uses, so a key cannot end up in a proxy log or an exception's URL.
            "x-goog-api-key": self._api_key,
        }

        self._pacer.wait_for_slot()
        try:
            response = self._client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as cause:
            raise transport_error(self.name, cause) from cause

        if response.status_code >= 400:
            raise status_error(self.name, response, hint=self._hint(response))

        try:
            data = response.json()
        except ValueError as cause:
            error = ProviderError(
                f"{self.name} answered with something that is not JSON: "
                f"{describe_response(response)}",
                provider=self.name,
                retryable=True,
            )
            error.status_code = response.status_code
            error.retry_after = None
            raise error from cause

        if not isinstance(data, dict):
            raise ProviderError(
                f"{self.name} answered with JSON that is not an object.",
                provider=self.name,
                retryable=True,
            )
        return data

    def _read(self, data: dict) -> _Reply:
        candidates = data.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            blocked = _block_reason(data)
            if blocked:
                # A safety block is a decision about this prompt, and repeating
                # it verbatim gets the same decision. Let the chain move on.
                raise ProviderError(
                    f"{self.name} refused the prompt ({blocked}).",
                    provider=self.name,
                    retryable=False,
                )
            raise ProviderError(
                f"{self.name} returned no candidates for {self.model}.",
                provider=self.name,
                retryable=True,
            )

        candidate = candidates[0] if isinstance(candidates[0], dict) else {}
        content = candidate.get("content")
        parts = content.get("parts") if isinstance(content, dict) else None
        text = "".join(
            part["text"]
            for part in (parts or [])
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )

        if not text.strip():
            reason = candidate.get("finishReason")
            detail = (
                " The answer hit maxOutputTokens before any text was produced."
                if reason == "MAX_TOKENS"
                else ""
            )
            raise ProviderError(
                f"{self.name} returned an empty completion "
                f"(finishReason={reason!r}).{detail}",
                provider=self.name,
                # SAFETY and RECITATION are verdicts on this prompt and will not
                # change on a second attempt; anything else might.
                retryable=reason not in {"SAFETY", "RECITATION", "BLOCKLIST"},
            )

        usage = data.get("usageMetadata")
        usage = usage if isinstance(usage, dict) else {}
        served = data.get("modelVersion")
        return _Reply(
            text=text,
            model=served if isinstance(served, str) and served else self.model,
            prompt_tokens=_token_count(usage.get("promptTokenCount")),
            completion_tokens=_token_count(usage.get("candidatesTokenCount")),
        )

    def _hint(self, response: httpx.Response) -> str | None:
        if response.status_code in {401, 403}:
            return f"That reads as a rejected key; check {self.api_key_env}."
        if response.status_code == 404:
            return (
                f"Check that {self.model!r} is still a current Gemini model; "
                "the catalogue changes between releases."
            )
        if response.status_code == 429:
            return "That is the free tier's per-minute or per-day limit."
        return None


def sanitise_schema(schema: Mapping) -> dict:
    """Translate a JSON Schema into the subset Gemini accepts.

    Local `$ref`s are inlined, because pydantic emits one for every nested model
    and Gemini resolves none of them. Unsupported keywords are dropped rather
    than approximated: a dropped constraint makes the request weaker, while a
    guessed one would make it wrong.
    """
    if not isinstance(schema, Mapping):
        raise UntranslatableSchema("a schema must be a mapping")
    return _translate(schema, root=schema, depth=0)


def _translate(node: Mapping, *, root: Mapping, depth: int) -> dict:
    if depth > _MAX_SCHEMA_DEPTH:
        raise UntranslatableSchema("schema nests deeper than Gemini allows")

    node = _resolve(node, root=root, depth=depth)
    result: dict = {}

    declared = node.get("type")
    nullable = False
    if isinstance(declared, list):
        # `["string", "null"]` is how an optional field arrives; Gemini spells
        # the same thing as one type plus a nullable flag.
        names = [name for name in declared if name != "null"]
        nullable = len(names) < len(declared)
        declared = names[0] if names else None
    if isinstance(declared, str):
        name = _TYPE_NAMES.get(declared.lower())
        if name is None:
            raise UntranslatableSchema(f"unknown type {declared!r}")
        result["type"] = name
    if nullable or node.get("nullable") is True:
        result["nullable"] = True

    for keyword in ("description", "enum", "required", "minItems", "maxItems"):
        if keyword in node:
            result[keyword] = node[keyword]
    for keyword in ("minLength", "maxLength", "pattern", "minimum", "maximum"):
        if keyword in node:
            result[keyword] = node[keyword]

    if isinstance(node.get("format"), str) and node["format"] in _SUPPORTED_FORMATS:
        result["format"] = node["format"]

    properties = node.get("properties")
    if isinstance(properties, Mapping):
        result["properties"] = {
            key: _translate(value, root=root, depth=depth + 1)
            for key, value in properties.items()
            if isinstance(value, Mapping)
        }
        # Field order is not a constraint in JSON Schema but is one here, and
        # keeping the declared order makes a reply easier to read beside the
        # model that defined it.
        result.setdefault("propertyOrdering", list(result["properties"]))

    items = node.get("items")
    if isinstance(items, Mapping):
        result["items"] = _translate(items, root=root, depth=depth + 1)

    variants = node.get("anyOf") or node.get("oneOf")
    if isinstance(variants, list):
        translated = [
            _translate(variant, root=root, depth=depth + 1)
            for variant in variants
            if isinstance(variant, Mapping) and variant.get("type") != "null"
        ]
        if not translated:
            raise UntranslatableSchema("a union with no usable member")
        if len(translated) == 1:
            result = {**translated[0], **result}
        else:
            result["anyOf"] = translated
        if len(translated) < len(variants):
            result["nullable"] = True

    if not result:
        raise UntranslatableSchema("a schema with nothing Gemini understands")
    return {key: value for key, value in result.items() if key in _SUPPORTED_KEYWORDS}


def _resolve(node: Mapping, *, root: Mapping, depth: int) -> Mapping:
    """Follow a local `$ref` and flatten a single-member `allOf`.

    Both are pydantic's doing rather than the schema author's: a nested model
    becomes a `$ref`, and a `$ref` carrying a description becomes an `allOf`
    with one member.
    """
    seen: set[str] = set()
    while True:
        reference = node.get("$ref")
        if isinstance(reference, str):
            if reference in seen:
                raise UntranslatableSchema(f"{reference} refers to itself")
            seen.add(reference)
            node = {**_lookup(reference, root), **_without(node, "$ref")}
            continue

        members = node.get("allOf")
        if isinstance(members, list) and len(members) == 1:
            member = members[0]
            if not isinstance(member, Mapping):
                raise UntranslatableSchema("allOf holds something that is not a schema")
            node = {**member, **_without(node, "allOf")}
            continue

        if isinstance(members, list):
            raise UntranslatableSchema("Gemini has no equivalent of a multi-part allOf")
        return node


def _lookup(reference: str, root: Mapping) -> Mapping:
    if not reference.startswith("#/"):
        raise UntranslatableSchema(f"{reference} is not a local reference")
    target: object = root
    for step in reference[2:].split("/"):
        step = step.replace("~1", "/").replace("~0", "~")
        if not isinstance(target, Mapping) or step not in target:
            raise UntranslatableSchema(f"{reference} does not resolve")
        target = target[step]
    if not isinstance(target, Mapping):
        raise UntranslatableSchema(f"{reference} does not point at a schema")
    return target


def _without(node: Mapping, keyword: str) -> dict:
    return {key: value for key, value in node.items() if key != keyword}


def _block_reason(data: Mapping) -> str | None:
    feedback = data.get("promptFeedback")
    if isinstance(feedback, Mapping) and feedback.get("blockReason"):
        return str(feedback["blockReason"])
    return None


def _token_count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


__all__ = [
    "API_KEY_ENVIRONMENT",
    "DEFAULT_BASE_URL",
    "GeminiProvider",
    "UntranslatableSchema",
    "json_instruction",
    "sanitise_schema",
]
