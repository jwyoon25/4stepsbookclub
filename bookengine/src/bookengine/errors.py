"""The failures this engine is allowed to have.

Every one of these is a refusal to produce educational material the engine
cannot stand behind. They carry enough detail for an operator to act: which
book, which chapter, which lesson, which item, and what would have to change.
"""

from __future__ import annotations


class BookEngineError(Exception):
    """Base class for every deliberate failure in the engine."""


class SourceError(BookEngineError):
    """The book could not be turned into a trustworthy source of truth."""


class UnsupportedBookError(SourceError):
    """The PDF is outside what this version supports.

    Raised for image-only scans and for extraction so poor that nothing built
    on top of it could be verified. The correct answer is "unsupported book",
    never a guess.
    """


class ChapterDetectionError(SourceError):
    """Chapter structure could not be established with confidence.

    Generating against a misread chapter map would put the wrong chapter number
    on a workbook page, so detection failing is a full stop.
    """


class ConfigError(BookEngineError):
    """A job description the engine cannot honour."""


class ProviderError(BookEngineError):
    """One inference provider failed. The chain may still succeed."""

    def __init__(self, message: str, *, provider: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class ProviderChainError(BookEngineError):
    """Every configured provider failed for one call.

    `attempts` carries what each provider actually said, so a caller can tell a
    rate limit from a rejected key without reading the message.
    """

    attempts: list = []


class StructuredResponseError(BookEngineError):
    """A model returned something that is not the requested shape."""


class VerificationError(BookEngineError):
    """A deterministic check that must hold did not hold.

    This is a bug guard, not a content outcome: a candidate failing validation
    is ordinary and gets replaced. This is raised when the engine catches
    *itself* about to export something unverified.
    """


class GenerationIncompleteError(BookEngineError):
    """The run could not reach the requested number of verified items."""
