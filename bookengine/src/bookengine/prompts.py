"""Loading the prompt files, and substituting into them safely.

Prompts live in `prompts/` as Markdown rather than as string literals, because
they are the part of this engine most likely to be edited by someone who is not
editing code, and because a diff on a prompt should read like a diff on a
document.

Substitution deliberately does not use `str.format`. Prompt files contain JSON
examples, and `format` treats every brace in them as a field; one example object
would make the whole file unrenderable. Only `{lower_case_names}` are replaced,
and an unknown one is an error rather than a silently empty prompt — a prompt
missing its source text still looks like a prompt, and the model would answer it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .errors import BookEngineError

PROMPT_DIRECTORY = Path(__file__).resolve().parents[2] / "prompts"

_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")
_SYSTEM_HEADING = re.compile(r"^##\s+system\s*$", re.IGNORECASE | re.MULTILINE)
_USER_HEADING = re.compile(r"^##\s+user\s*$", re.IGNORECASE | re.MULTILINE)

DEFAULT_SYSTEM = (
    "You are a careful assistant working inside a verification pipeline. "
    "Answer only with the JSON described, and never invent source material: "
    "anything you assert about the book that is not in the text supplied to you "
    "will be discarded by the system that called you."
)


class PromptError(BookEngineError):
    """A prompt file that cannot be rendered as asked."""


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    """One prompt, split into the two messages a chat model expects."""

    system: str
    user: str


@lru_cache(maxsize=32)
def _read(directory: Path, name: str) -> str:
    path = directory / f"{name}.md"
    if not path.is_file():
        raise PromptError(
            f"No prompt named {name!r} in {directory}. Expected {path.name}."
        )
    return path.read_text(encoding="utf-8")


@dataclass(frozen=True, slots=True)
class PromptLibrary:
    """The prompt files, rendered on demand."""

    directory: Path = PROMPT_DIRECTORY

    def render(self, name: str, /, **values: object) -> RenderedPrompt:
        """Fill in one prompt and split it into system and user messages.

        A file may mark its system message with a `## System` heading; without
        one, the whole file is the user message and a shared default system
        message is used. Both shapes are supported because the split is a detail
        of how models are addressed, not something a prompt author should have
        to remember.
        """
        text = _read(self.directory, name)
        missing: list[str] = []

        def substitute(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in values:
                missing.append(key)
                return match.group(0)
            return str(values[key])

        rendered = _PLACEHOLDER.sub(substitute, text)
        if missing:
            raise PromptError(
                f"{name}.md expects "
                + ", ".join(sorted(set(missing)))
                + ", which the caller did not supply."
            )

        return _split(rendered)

    def placeholders(self, name: str) -> set[str]:
        """Every placeholder a prompt file uses, for checking wiring in tests."""
        return set(_PLACEHOLDER.findall(_read(self.directory, name)))

    def names(self) -> list[str]:
        return sorted(path.stem for path in self.directory.glob("*.md"))


def _split(text: str) -> RenderedPrompt:
    system_match = _SYSTEM_HEADING.search(text)
    if system_match is None:
        return RenderedPrompt(system=DEFAULT_SYSTEM, user=text.strip())

    remainder = text[system_match.end() :]
    user_match = _USER_HEADING.search(remainder)
    if user_match is None:
        return RenderedPrompt(
            system=remainder.strip(), user=text[: system_match.start()].strip()
        )

    return RenderedPrompt(
        system=remainder[: user_match.start()].strip(),
        user=remainder[user_match.end() :].strip(),
    )
