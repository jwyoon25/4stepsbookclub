"""Workers AI, which is the OpenAI shape behind an account-scoped URL.

Cloudflare earns a module rather than a line in `KNOWN_ENDPOINTS` for one
reason: its endpoint contains the account id, so the base URL cannot be a
constant. Everything past that is the request body this engine already sends —
`/chat/completions`, `response_format` with a real JSON schema, `choices[0]
.message.content` back, and a `model` field that echoes what was served. So
this subclasses the OpenAI adapter instead of restating it. Forcing a provider
into an abstraction it does not fit would be wrong; declining to reuse one it
does fit is just duplication waiting to drift.

The one addition is `neurons`. Cloudflare meters Workers AI in them rather than
in tokens, the free plan is a daily allowance of them, and the number comes back
on every response — so it is read here and carried on the `Completion`. A run
that wants to know whether a workbook fits inside the free allowance can then
ask the completions rather than a pricing table.
"""

from __future__ import annotations

import os

import httpx

from ..config import ProviderConfig
from ..errors import ConfigError
from .openai_compatible import OpenAICompatibleProvider

# Where the account id comes from. Named for the variable Cloudflare's own
# documentation and dashboard use, so an operator who has one exported for
# `wrangler` needs to do nothing else.
ACCOUNT_ENVIRONMENT = "CLOUDFLARE_ACCOUNT_ID"
API_KEY_ENVIRONMENT = "CLOUDFLARE_API_TOKEN"

API_ROOT = "https://api.cloudflare.com/client/v4/accounts"

# The OpenAI-compatible path under the account. Workers AI also serves a native
# per-model route, which this engine has no use for: the compatible one accepts
# the body it already builds.
OPENAI_PATH = "ai/v1"


def account_id(config: ProviderConfig) -> str:
    """The Cloudflare account this provider talks to.

    An account id is not a secret in the way a token is, but it is still not
    something to commit, so it comes from the environment and the job file
    names only the model.
    """
    found = os.environ.get(ACCOUNT_ENVIRONMENT, "").strip()
    if found:
        return found
    raise ConfigError(
        f"Cloudflare needs an account id but {ACCOUNT_ENVIRONMENT} is not set "
        f"in the environment. Export it, for example "
        f"`export {ACCOUNT_ENVIRONMENT}=...`. It is on the right of the "
        "Workers & Pages overview in the dashboard."
    )


class CloudflareProvider(OpenAICompatibleProvider):
    """One Workers AI model, reached through the OpenAI-compatible route."""

    # Cloudflare's meter. Read from `usage` and carried on the completion so a
    # caller can total the free plan's daily allowance from real answers.
    usage_units_key = "neurons"

    def __init__(
        self, config: ProviderConfig, *, client: httpx.Client | None = None
    ) -> None:
        base_url = config.base_url or (
            f"{API_ROOT}/{account_id(config)}/{OPENAI_PATH}"
        )
        super().__init__(
            config.model_copy(
                update={
                    "base_url": base_url,
                    "api_key_env": config.api_key_env or API_KEY_ENVIRONMENT,
                }
            ),
            client=client,
        )

    def _hint(self, response: httpx.Response) -> str | None:
        """What an operator should check, in Cloudflare's own vocabulary."""
        if response.status_code in {401, 403}:
            return (
                f"Check {API_KEY_ENVIRONMENT} — the token needs the Workers AI "
                f"read/run permission — and that {ACCOUNT_ENVIRONMENT} is the "
                "account that token belongs to."
            )
        if response.status_code == 404:
            return (
                f"Check that {self.model!r} is still in this account's "
                "catalogue. Workers AI model ids start with `@cf/` and are "
                "listed at /ai/models/search."
            )
        # No branch for 429 here. `status_error` prints a hint only when
        # waiting cannot fix the problem, so one written for the rate limit
        # would never be read. What the Free plan's daily Neuron allowance
        # running out looks like belongs in the smoke report, where somebody is
        # actually looking at quotas.
        return super()._hint(response)
