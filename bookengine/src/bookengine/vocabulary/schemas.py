"""The shapes an LLM answer is allowed to arrive in, and the ones it is not.

A prompt that asks a model to be truthful is a request. A response schema is a
constraint, and this is where the engine's central rule stops being a sentence
in a document and becomes something a model has no route around: there is no
field in this file that carries a quotation from the book, and none that
carries a chapter number.

That is the whole design. A model may say which word is worth teaching, which
of the book's own sentences teaches it best, and what the word means. Both
facts a reader would check against the book — the quoted passage and the
chapter it came from — are cut from the source at a locator in
`source/excerpt.py`, so a fabricated quotation is not caught late, it is
unsayable. Editing a prompt cannot change that; only editing this file could.

These are pydantic models rather than the dataclasses used elsewhere because
this is the boundary where untrusted data arrives. Past this point the pipeline
works with `vocabulary/models.py` and may assume the fields are the right shape
and already inside the workbook's own limits.

The checks here are about shape alone. Whether a proposed word occurs in the
chapter range, whether an excerpt really is the book's text, whether a Korean
meaning contains any Korean: those are questions about the world, and the
engine answers them in code against the source rather than trusting an answer
for arriving well formed.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# These mirror the vocabulary entry in workbooks/schema/lesson.schema.json. A
# value past one of them is not a matter of taste: the workbook builder rejects
# the row, so anything generated over the limit was wasted work. Catching it
# here means the model is asked again while the run is still cheap to redo.
TERM_LIMIT = 60
KOREAN_MEANING_LIMIT = 100
DEFINITION_LIMIT = 600
EXCERPT_CONTEXT_LIMIT = 700

# Short free-text fields the engine reads but the workbook never prints. They
# are capped so that a model which starts writing an essay fails fast instead
# of filling a log.
REASON_LIMIT = 240
NOTE_LIMIT = 400

# The auditor's vocabulary. Written as literals so a verdict of "mostly fine"
# fails validation rather than reaching an operator who has to guess what it
# meant. The wording in prompts/audit.md must list exactly these values.
Verdict = Literal["PASS", "FAIL"]
DifficultyFit = Literal["TOO_EASY", "APPROPRIATE", "TOO_HARD"]
Accuracy = Literal["ACCURATE", "MINOR_ISSUE", "INACCURATE"]
ExcerptFit = Literal["GOOD", "WEAK", "POOR"]


class _Answer(BaseModel):
    """One model answer, held to exactly the fields that were asked for.

    `extra="forbid"` matters more than it looks: a model that volunteers an
    `excerpt` or a `chapter` field is refused rather than half-accepted, so an
    unused extra field can never quietly become a supported one.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CandidateWord(_Answer):
    """One word a model proposes teaching from a lesson's reading."""

    term: str = Field(
        min_length=1,
        max_length=TERM_LIMIT,
        description=(
            "The word itself, spelled as it appears in the supplied text. Give "
            "the word alone, not a phrase and not a sentence."
        ),
    )
    reason: str = Field(
        min_length=1,
        max_length=REASON_LIMIT,
        description="One short sentence on why this word is worth teaching.",
    )
    sense: str = Field(
        min_length=1,
        max_length=REASON_LIMIT,
        description=(
            "The meaning the word carries in this book, not every meaning it "
            "has. A few words are enough."
        ),
    )


class CandidateList(_Answer):
    """A whole proposal for one lesson."""

    # An empty list is treated as a failed call rather than a result: every
    # chapter range of a novel contains teachable words, so "none" means the
    # model did not answer the question and should be asked again.
    candidates: list[CandidateWord] = Field(
        min_length=1,
        max_length=400,
        description="The proposed words, best first.",
    )


class RankedWord(_Answer):
    """One candidate scored against the rubric.

    Five dimensions read the same way — higher is better — and the sixth does
    not. That asymmetry is deliberate and is spelled out in the field
    description, because the description is the part the model sees.
    """

    term: str = Field(
        min_length=1,
        max_length=TERM_LIMIT,
        description="The candidate word being scored, copied exactly.",
    )
    difficulty: int = Field(
        ge=1,
        le=5,
        description=(
            "How much of a stretch this word is for the audience. 1 means they "
            "already know it, 5 means a demanding word that is still within "
            "reach. A word beyond reach is not a 5: score it low here and high "
            "on exclusion_risk."
        ),
    )
    general_utility: int = Field(
        ge=1,
        le=5,
        description=(
            "How often the word repays a student outside this book, in their "
            "own reading, writing and exams. 5 is very widely useful."
        ),
    )
    context_quality: int = Field(
        ge=1,
        le=5,
        description=(
            "How well the book's own sentences make the meaning recoverable. "
            "5 means a reader could work the word out from the passage."
        ),
    )
    educational_value: int = Field(
        ge=1,
        le=5,
        description=(
            "How much a student gains from studying this particular word — a "
            "useful root, a common word family, a precise idea they lack a "
            "word for. 5 is high."
        ),
    )
    generality: int = Field(
        ge=1,
        le=5,
        description=(
            "How far the sense travels beyond this scene. 5 is a general sense "
            "that works anywhere; 1 is tied to one moment, one idiom, or one "
            "invented use in this book."
        ),
    )
    exclusion_risk: int = Field(
        ge=1,
        le=5,
        description=(
            "HIGH IS BAD. How likely it is that this word should not be taught "
            "at all: a proper noun or character name, a word invented for this "
            "book, narrow jargon, an archaic word with no present-day use, "
            "something offensive, or a word far beyond the audience. 1 means no "
            "concern; 5 means do not teach it."
        ),
    )
    note: str | None = Field(
        default=None,
        max_length=NOTE_LIMIT,
        description="Anything a person should know about this score. Optional.",
    )


class RankedList(_Answer):
    """Scores for the candidates that were sent for ranking."""

    ranked: list[RankedWord] = Field(
        min_length=1,
        max_length=400,
        description="One entry per candidate word that was supplied.",
    )


class OccurrenceChoice(_Answer):
    """Which of the book's own occurrences should teach the word.

    The index is the entire interface a model has to the book's text here. It
    picks a row out of a list the engine built from the source, and the engine
    then cuts the passage itself.
    """

    index: int = Field(
        ge=0,
        description=(
            "The number of the occurrence you chose, exactly as it is printed "
            "in the numbered list."
        ),
    )
    reason: str = Field(
        min_length=1,
        max_length=REASON_LIMIT,
        description="One short sentence on why that occurrence teaches it best.",
    )


class EntryDraft(_Answer):
    """The written part of a workbook row: the part no book contains.

    Everything here is genuinely the model's own work — a definition of the
    sense used in this passage, its Korean equivalent, and what is happening in
    the story. There is no excerpt field and no chapter field, because both of
    those come from the source and would only be a second, unverifiable copy.
    """

    definition: str = Field(
        min_length=1,
        max_length=DEFINITION_LIMIT,
        description=(
            "A student-facing English definition of the sense used in this "
            "passage. One or two plain sentences; do not use the word itself "
            "inside its own definition."
        ),
    )
    korean_meaning: str = Field(
        min_length=1,
        max_length=KOREAN_MEANING_LIMIT,
        description=(
            "The natural Korean meaning of that same sense, written in Korean. "
            "Short: a word or a short phrase, no romanisation."
        ),
    )
    excerpt_context: str = Field(
        min_length=1,
        max_length=EXCERPT_CONTEXT_LIMIT,
        description=(
            "One sentence saying what is happening in the story around this "
            "passage, so a student can place the moment. It is not a "
            "definition, a usage note, or an explanation of the word."
        ),
    )


class AuditItemVerdict(_Answer):
    """An independent judgement of one finished row."""

    word: str = Field(
        min_length=1,
        max_length=TERM_LIMIT,
        description="The vocabulary word this verdict is about, copied exactly.",
    )
    verdict: Verdict = Field(
        description=(
            "PASS if the row can go to a student as it stands. FAIL if any part "
            "of it is wrong, misleading, or wrong for the audience."
        )
    )
    difficulty: DifficultyFit = Field(
        description="Whether the word suits the stated audience."
    )
    definition_accuracy: Accuracy = Field(
        description=(
            "Whether the English definition matches the sense the word carries "
            "in the supplied passage."
        )
    )
    korean_accuracy: Accuracy = Field(
        description=(
            "Whether the Korean meaning is a correct and natural rendering of "
            "that same sense."
        )
    )
    context_accuracy: Accuracy = Field(
        description=(
            "Whether the story context describes what the supplied passage and "
            "surrounding paragraphs actually show."
        )
    )
    excerpt_fit: ExcerptFit = Field(
        description=(
            "How well the passage teaches the word: GOOD if the meaning is "
            "recoverable from it, WEAK if it barely helps, POOR if it does not "
            "teach the word at all."
        )
    )
    # A FAIL with no reason is nearly useless to the person who has to act on
    # it, and prompts/audit.md asks for one. It is not required here on
    # purpose: refusing the answer would throw away a correct FAIL verdict, and
    # losing a real failure is worse than losing its explanation.
    notes: str | None = Field(
        default=None,
        max_length=NOTE_LIMIT,
        description=(
            "What is wrong and what would fix it. Required in practice whenever "
            "the verdict is FAIL or anything is less than ACCURATE."
        ),
    )


class AuditReport(_Answer):
    """One auditor's verdicts on a batch of rows."""

    items: list[AuditItemVerdict] = Field(
        min_length=1,
        max_length=200,
        description="One verdict for every row that was supplied, in any order.",
    )


# Keywords that carry nothing for a model and that some strict validators
# refuse outright.
_SCHEMA_NOISE = frozenset({"title", "default"})

# Keys whose values are a mapping of names to schemas rather than a schema, so
# their keys must not be treated as JSON Schema keywords.
_SCHEMA_MAPS = frozenset({"properties", "patternProperties"})


def json_schema_for(model: type[BaseModel]) -> dict:
    """A provider-ready JSON schema for one of these models.

    Pydantic emits `$defs` and `$ref` for nested models, and several of the
    free providers this engine falls back on reject a schema containing either.
    The nesting here is shallow and never recursive, so the references are
    resolved inline. Doing it this way rather than keeping hand-written schemas
    beside the models is the point: two definitions of one shape drift, and the
    one that drifts would be the one the provider enforces.

    Two other adjustments serve the same awkward audience. `title` and
    `default` are dropped, since they tell a model nothing and strict
    validators refuse keywords they did not expect. And every property is
    listed as required, because the strictest structured-output modes demand
    it; nothing is lost, as the optional fields are nullable and "no note" is
    still sayable as null.
    """
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})
    return _resolve(schema, definitions, ())


def _resolve(node: Any, definitions: dict, stack: tuple[str, ...]) -> Any:
    """Walk a schema, inlining references and tightening objects as it goes."""
    if isinstance(node, list):
        return [_resolve(item, definitions, stack) for item in node]
    if not isinstance(node, dict):
        return node

    if "$ref" in node:
        name = str(node["$ref"]).rsplit("/", 1)[-1]
        if name in stack:
            raise ValueError(
                f"{name} refers to itself. This function inlines references, "
                "so a recursive model would never finish; keep these shapes flat."
            )
        if name not in definitions:
            raise ValueError(f"The schema refers to {name}, which is not defined.")
        resolved = _resolve(definitions[name], definitions, (*stack, name))
        # Anything sitting beside the reference — a description, usually —
        # belongs to this use of the shape, so it wins over the definition.
        beside = {
            key: _resolve(value, definitions, stack)
            for key, value in node.items()
            if key != "$ref" and key not in _SCHEMA_NOISE
        }
        return {**resolved, **beside}

    result: dict[str, Any] = {}
    for key, value in node.items():
        if key in _SCHEMA_NOISE:
            continue
        if key in _SCHEMA_MAPS and isinstance(value, dict):
            result[key] = {
                name: _resolve(subschema, definitions, stack)
                for name, subschema in value.items()
            }
        else:
            result[key] = _resolve(value, definitions, stack)

    if result.get("type") == "object" and "properties" in result:
        result["additionalProperties"] = False
        result["required"] = list(result["properties"])

    return result
