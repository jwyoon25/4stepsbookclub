"""Remembering what a model already said about an identical prompt.

Two things make this worth having. Free endpoints are rate-limited, so a run
that fails at lesson four should not have to re-ask lesson one when it is
restarted. And a job re-run after an excerpt setting changed should only pay for
the calls that actually changed, which is what makes iterating on a book
affordable at zero marginal cost.

Only successes are stored. Caching a failure would turn a transient rate limit
into a permanent one, and the operator would have no way to tell that the empty
answer they keep getting is a week-old timeout.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .base import Completion, Message

# Bumped when the stored shape changes. An entry written by an older version is
# a miss rather than a crash.
CACHE_FORMAT_VERSION = 1


@dataclass(frozen=True, slots=True)
class ResponseCache:
    """A directory of answers, keyed by everything that produced them."""

    directory: Path
    enabled: bool = True

    def key(
        self,
        *,
        provider: str,
        model: str,
        messages: list[Message],
        json_schema: dict | None,
        temperature: float | None,
        max_output_tokens: int | None,
    ) -> str:
        """The identity of one call.

        Everything that could change the answer is in the key, including the
        schema: the same prompt asked with and without a schema is two
        questions, and free endpoints answer them differently.
        """
        payload = json.dumps(
            {
                "version": CACHE_FORMAT_VERSION,
                "provider": provider,
                "model": model,
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
                "messages": [
                    {"role": message.role, "content": message.content}
                    for message in messages
                ],
                "schema": json_schema,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def path_for(self, key: str) -> Path:
        # One level of fan-out, so a long run does not put ten thousand files
        # in one directory.
        return self.directory / key[:2] / f"{key}.json"

    def load(self, key: str) -> Completion | None:
        if not self.enabled:
            return None
        path = self.path_for(key)
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if stored.get("version") != CACHE_FORMAT_VERSION:
            return None
        try:
            return Completion(
                text=stored["text"],
                provider=stored["provider"],
                model=stored["model"],
                prompt_tokens=stored.get("prompt_tokens"),
                completion_tokens=stored.get("completion_tokens"),
                cached=True,
                schema_mode=stored.get("schema_mode"),
            )
        except KeyError:
            return None

    def store(self, key: str, completion: Completion) -> None:
        if not self.enabled:
            return
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".partial")
        partial.write_text(
            json.dumps(
                {
                    "version": CACHE_FORMAT_VERSION,
                    "stored_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "text": completion.text,
                    "provider": completion.provider,
                    "model": completion.model,
                    "prompt_tokens": completion.prompt_tokens,
                    "completion_tokens": completion.completion_tokens,
                    "schema_mode": completion.schema_mode,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        # Replace is atomic, so an interrupted run cannot leave half an answer
        # that later loads as a whole one.
        partial.replace(path)

    def clear(self) -> int:
        removed = 0
        if not self.directory.is_dir():
            return removed
        for path in self.directory.rglob("*.json"):
            path.unlink(missing_ok=True)
            removed += 1
        return removed
