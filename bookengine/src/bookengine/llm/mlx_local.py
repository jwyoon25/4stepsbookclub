"""The local last resort, for a day when every free endpoint says no.

Apple Silicon can run a capable model locally, and `mlx_lm.server` serves it at
an OpenAI-compatible endpoint. That is the whole reason this adapter is thirty
lines instead of three hundred: the local fallback is a base URL, not a new
protocol, so it inherits every retry, schema-mode fallback and error message the
hosted adapters already have.

`mlx` is deliberately not imported. Importing it would make an optional extra a
hard dependency of the module graph, and the engine has to install and run on a
machine that will never do local inference.
"""

from __future__ import annotations

import httpx

from ..config import ProviderConfig
from ..errors import ProviderError
from .openai_compatible import OpenAICompatibleProvider

DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"

START_HINT = (
    "Start it with `mlx_lm.server --model <model-id> --port 8080`, or point "
    "`base_url:` at wherever it is already listening."
)


class MLXLocalProvider(OpenAICompatibleProvider):
    """A locally served model, addressed as an OpenAI-compatible endpoint."""

    def __init__(
        self, config: ProviderConfig, *, client: httpx.Client | None = None
    ) -> None:
        super().__init__(
            config,
            client=client,
            # A local server has no key, and demanding one would make the
            # fallback unusable at exactly the moment it is needed.
            require_api_key=False,
            default_base_url=DEFAULT_BASE_URL,
        )

    def complete(self, messages, **kwargs):
        try:
            return super().complete(messages, **kwargs)
        except ProviderError as error:
            # A local server that is not running fails as a connection error,
            # which reads like a network problem and is not one.
            if getattr(error, "status_code", None) is None:
                raise ProviderError(
                    f"No local model server is answering at {self.base_url}. "
                    f"{START_HINT}",
                    provider=self.name,
                    retryable=False,
                ) from error
            raise
