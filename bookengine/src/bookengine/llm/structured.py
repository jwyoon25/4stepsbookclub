"""Getting a shape back from a model, or getting nothing back at all.

Free endpoints are inconsistent about structured output. Some honour a JSON
schema, some honour "respond with JSON", some do neither and wrap the answer in
a Markdown fence with a sentence of preamble. Parsing prose is not an option
here — a mis-parsed audit verdict would mark a failed item as passed — so this
module does three things and then gives up loudly.

It extracts JSON from whatever wrapping came back. It validates against a
pydantic model. And when validation fails it sends the validation error back to
the model once or twice, which is the one repair strategy that works reliably
across endpoints, because it turns "your answer was wrong" into a concrete
instruction. After that it raises, with the raw text attached, because a
malformed answer that is allowed to propagate is indistinguishable downstream
from a correct one.
"""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..errors import StructuredResponseError
from ..vocabulary.schemas import json_schema_for
from .base import Completion, Message
from .chain import ProviderChain

Model = TypeVar("Model", bound=BaseModel)

_FENCE = re.compile(r"```(?:json)?\s*(?P<body>.+?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> str:
    """Find the JSON in a reply that may be wearing a jacket.

    Tried in order: the whole string, a fenced block, and the first balanced
    object or array. The balanced scan is what handles a model that opens with
    "Here is the JSON you asked for:" — common enough on free endpoints that
    failing on it would fail most runs.
    """
    stripped = text.strip()
    if not stripped:
        raise StructuredResponseError("The model returned an empty response.")

    if stripped[0] in "{[":
        return stripped

    fenced = _FENCE.search(stripped)
    if fenced:
        return fenced.group("body").strip()

    for opening, closing in (("{", "}"), ("[", "]")):
        start = stripped.find(opening)
        if start == -1:
            continue
        depth, in_string, escaped = 0, False, False
        for index in range(start, len(stripped)):
            character = stripped[index]
            if in_string:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    in_string = False
                continue
            if character == '"':
                in_string = True
            elif character == opening:
                depth += 1
            elif character == closing:
                depth -= 1
                if depth == 0:
                    return stripped[start : index + 1]

    raise StructuredResponseError(
        "The model's response contains no JSON.\n"
        f"It said: {stripped[:400]}"
    )


def parse_into(text: str, model_type: type[Model]) -> Model:
    """Validate one reply against the shape it was asked for."""
    body = extract_json(text)
    try:
        payload = json.loads(body)
    except ValueError as cause:
        raise StructuredResponseError(
            f"The reply is not valid JSON: {cause}"
        ) from cause

    try:
        return model_type.model_validate(payload)
    except ValidationError as cause:
        raise StructuredResponseError(str(cause)) from cause


def generate_structured(
    chain: ProviderChain,
    messages: list[Message],
    model_type: type[Model],
    *,
    json_schema: dict | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
    max_repairs: int = 2,
) -> tuple[Model, Completion]:
    """Ask for a shape and keep asking until it arrives or the budget runs out.

    The repair turn quotes the model's own answer back at it alongside the
    validation error. That matters: a model told only "invalid JSON" will often
    produce a different invalid answer, and one shown the offending field will
    usually fix that field.
    """
    schema = json_schema if json_schema is not None else json_schema_for(model_type)
    conversation = list(messages)
    problems: list[str] = []

    for attempt in range(max_repairs + 1):
        completion = chain.complete(
            conversation,
            json_schema=schema,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        try:
            return parse_into(completion.text, model_type), completion
        except StructuredResponseError as failure:
            problems.append(str(failure))
            if attempt == max_repairs:
                raise StructuredResponseError(
                    f"{chain.primary.name} did not return the requested shape "
                    f"after {max_repairs + 1} attempts.\n"
                    + "\n".join(f"  - {problem}" for problem in problems)
                    + f"\nLast reply: {completion.text[:600]}"
                ) from failure

            conversation = [
                *messages,
                Message(role="assistant", content=completion.text[:4000]),
                Message(
                    role="user",
                    content=(
                        "That response did not match the required shape. The "
                        f"validator said:\n{failure}\n\n"
                        "Send the corrected JSON only, with no explanation and "
                        "no code fence."
                    ),
                ),
            ]

    raise StructuredResponseError("unreachable")  # pragma: no cover
