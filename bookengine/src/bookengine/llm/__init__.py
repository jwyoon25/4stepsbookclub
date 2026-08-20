"""Inference, behind one interface that knows nothing about vocabulary."""

from .base import Completion, LLMProvider, Message
from .cache import ResponseCache
from .chain import ProviderChain
from .gemini import GeminiProvider
from .mlx_local import MLXLocalProvider
from .openai_compatible import KNOWN_ENDPOINTS, OpenAICompatibleProvider
from .registry import build_chains, build_provider
from .structured import extract_json, generate_structured, parse_into

__all__ = [
    "KNOWN_ENDPOINTS",
    "Completion",
    "GeminiProvider",
    "LLMProvider",
    "MLXLocalProvider",
    "Message",
    "OpenAICompatibleProvider",
    "ProviderChain",
    "ResponseCache",
    "build_chains",
    "build_provider",
    "extract_json",
    "generate_structured",
    "parse_into",
]
