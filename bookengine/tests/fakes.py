"""A model that answers, without a network and without a bill.

Every pipeline test runs against this. It answers each prompt by the shape it
was asked for, which is enough to exercise the whole run, and it can be told to
misbehave in the specific ways real endpoints misbehave: fabricate a quotation,
claim the wrong chapter, propose a word the book does not contain, return
malformed JSON, or fail a healthy item at audit.

The point of the misbehaviour switches is that the engine's guarantees are meant
to hold against a hostile model, not a cooperative one. A test suite that only
ever sees good answers proves nothing about the part of the design that matters.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from bookengine.errors import ProviderError
from bookengine.llm.base import Completion, Message


def _schema_kind(json_schema: dict | None, messages: list[Message]) -> str:
    """Work out which stage is asking."""
    properties = set((json_schema or {}).get("properties", {}))
    if "ranked" in properties:
        return "ranking"
    if "index" in properties:
        return "occurrence"
    if "definition" in properties:
        return "entry"
    if "candidates" in properties:
        return "candidates"
    if "items" in properties:
        return "audit"
    # Without a usable schema, fall back to what the prompt says it wants.
    text = " ".join(message.content for message in messages).lower()
    for name in ("ranked", "index", "definition", "candidates", "items"):
        if f'"{name}"' in text:
            return {"ranked": "ranking", "index": "occurrence"}.get(name, name)
    return "unknown"


def _section(text: str, heading: str) -> str:
    """One `## Heading` section of a rendered prompt.

    The prompts use bulleted instructions of their own, so a fake that scanned
    the whole message for `- word: example` would read the instructions as
    candidates and score the wrong things.
    """
    lines = text.splitlines()
    try:
        start = next(
            index
            for index, line in enumerate(lines)
            if line.strip().lower() == f"## {heading}".lower()
        )
    except StopIteration:
        return ""
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            return "\n".join(lines[start + 1 : index])
    return "\n".join(lines[start + 1 :])


def _terms_in(messages: list[Message]) -> list[str]:
    """The candidate words a ranking prompt listed, in order."""
    terms: list[str] = []
    for line in _section(messages[-1].content, "The candidates").splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and ":" in stripped:
            terms.append(stripped[2:].split(":", 1)[0].strip())
    return terms


def _audited_words(messages: list[Message]) -> list[str]:
    words: list[str] = []
    for line in messages[-1].content.splitlines():
        if line.startswith("Word: "):
            words.append(line[len("Word: ") :].strip())
    return words


@dataclass
class ScriptedProvider:
    """A provider that answers correctly unless told to do otherwise."""

    name: str = "fake"
    model: str = "scripted-1"
    # Words the auditor should reject, by normalized term.
    fail_audit: set[str] = field(default_factory=set)
    # Return an index outside the shortlist for every occurrence choice.
    bad_occurrence_index: bool = False
    # Answer the first n calls with unparseable text.
    malformed_first: int = 0
    # Words to invent in `model` candidate mode that are not in the book.
    invented_words: list[str] = field(default_factory=list)
    # Raise this many retryable errors before answering.
    fail_first: int = 0
    # Score every word this way; exclusion_risk is the interesting one.
    exclusion_risk: int = 1
    calls: list[str] = field(default_factory=list)

    def complete(
        self,
        messages: list[Message],
        *,
        json_schema: dict | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> Completion:
        if self.fail_first > 0:
            self.fail_first -= 1
            raise ProviderError(
                "fake rate limit", provider=self.name, retryable=True
            )

        kind = _schema_kind(json_schema, messages)
        self.calls.append(kind)

        if self.malformed_first > 0:
            self.malformed_first -= 1
            return self._reply("I'd be happy to help with that!")

        handler = getattr(self, f"_{kind}")
        return self._reply(json.dumps(handler(messages), ensure_ascii=False))

    def _reply(self, text: str) -> Completion:
        return Completion(
            text=text,
            provider=self.name,
            model=self.model,
            prompt_tokens=None,
            completion_tokens=None,
            schema_mode="json_schema",
        )

    def _ranking(self, messages: list[Message]) -> dict:
        return {
            "ranked": [
                {
                    "term": term,
                    "difficulty": 4,
                    "general_utility": 4,
                    "context_quality": 4,
                    "educational_value": 4,
                    "generality": 4,
                    "exclusion_risk": self.exclusion_risk,
                    "note": None,
                }
                for term in _terms_in(messages)
            ]
        }

    def _occurrence(self, messages: list[Message]) -> dict:
        return {
            "index": 999 if self.bad_occurrence_index else 0,
            "reason": "It shows the meaning without needing the page before it.",
        }

    def _entry(self, messages: list[Message]) -> dict:
        user = messages[-1].content
        term = "the word"
        for line in user.splitlines():
            if line.lower().startswith("word:"):
                term = line.split(":", 1)[1].strip()
                break
        return {
            "definition": f"a made-up student definition of {term}.",
            "korean_meaning": "임시 뜻",
            "excerpt_context": "Mara is trying to understand where she is.",
        }

    def _candidates(self, messages: list[Message]) -> dict:
        found = [
            word
            for word in ("predicament", "monotonous", "articulate", "deliberate")
            if word in messages[-1].content
        ]
        return {
            "candidates": [
                {"term": word, "reason": "useful", "sense": "the usual sense"}
                for word in [*found, *self.invented_words]
            ]
        }

    def _audit(self, messages: list[Message]) -> dict:
        return {
            "items": [
                {
                    "word": word,
                    "verdict": (
                        "FAIL" if word.lower() in self.fail_audit else "PASS"
                    ),
                    "difficulty": "APPROPRIATE",
                    "definition_accuracy": (
                        "INACCURATE" if word.lower() in self.fail_audit else "ACCURATE"
                    ),
                    "korean_accuracy": "ACCURATE",
                    "context_accuracy": "ACCURATE",
                    "excerpt_fit": "GOOD",
                    "notes": None,
                }
                for word in _audited_words(messages)
            ]
        }

    def _unknown(self, messages: list[Message]) -> dict:
        raise AssertionError(
            "The fake provider was asked something it does not recognise:\n"
            + messages[-1].content[:400]
        )

    def close(self) -> None:
        pass
