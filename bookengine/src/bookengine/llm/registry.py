"""Turning the job file's provider settings into objects that can be called.

This is the only module that maps a provider name to a class, which is what
keeps the rest of the engine free of provider knowledge. Adding SambaNova or
whatever replaces it next year is a line in a job file if it speaks the OpenAI
shape, and one entry here if it does not.

The generator and the auditor get separate chains on purpose. The audit stage is
worth having because it is independent, and independence is a property of the
configuration rather than of the prompt: two chains that start at different
providers make different mistakes, and a chain that fell back to the same
fallback for both has quietly stopped being an audit. That is why the run
records which model actually answered rather than which one was configured.
"""

from __future__ import annotations

from pathlib import Path

from ..config import LLMConfig, ProviderConfig
from .base import LLMProvider
from .cache import ResponseCache
from .chain import ProviderChain
from .gemini import GeminiProvider
from .mlx_local import MLXLocalProvider
from .openai_compatible import OpenAICompatibleProvider

# Providers whose wire format is not the OpenAI one, or that need different
# defaults. Everything absent from here is assumed OpenAI-compatible, which is
# what makes an unknown free provider usable without a code change.
_SPECIAL_CASES = {
    "gemini": GeminiProvider,
    "google": GeminiProvider,
    "mlx": MLXLocalProvider,
    "local": MLXLocalProvider,
}


def build_provider(config: ProviderConfig) -> LLMProvider:
    """Construct one endpoint from its configuration."""
    builder = _SPECIAL_CASES.get(config.provider.strip().lower())
    if builder is not None:
        return builder(config)
    return OpenAICompatibleProvider(config)


def build_chains(
    config: LLMConfig,
    *,
    cache_directory: Path | None = None,
) -> tuple[ProviderChain, ProviderChain]:
    """Build the generator chain and the auditor chain.

    Both fall back to the same list, because a fallback exists for the case
    where an endpoint is down and there is nothing else to reach for. The audit
    is weaker when that happens, and the run says so rather than pretending
    otherwise.
    """
    cache = (
        ResponseCache(directory=cache_directory, enabled=config.cache)
        if cache_directory is not None
        else None
    )
    fallbacks = [build_provider(entry) for entry in config.fallbacks]

    generator = ProviderChain(
        providers=[build_provider(config.generator), *fallbacks],
        max_attempts=config.max_attempts,
        cache=cache,
    )
    auditor = ProviderChain(
        providers=[build_provider(config.auditor), *fallbacks],
        max_attempts=config.max_attempts,
        cache=cache,
    )
    return generator, auditor
