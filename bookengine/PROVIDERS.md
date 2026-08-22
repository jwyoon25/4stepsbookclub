# Providers

Model ids and free allowances move faster than anything else in this engine, so
this file records what was **confirmed live on 2026-08-22** rather than what
documentation said. Re-run `bookengine smoke --config <job>` before trusting it
again; the smoke command is the check, this is the notebook.

Nothing here is legal advice. The data-use column is a pointer to each
provider's own current terms, recorded so the assumption is visible rather than
buried.

## What was confirmed live

Every model below answered a real structured request through this engine's own
adapters, returned valid JSON against a Pydantic schema, and reported back the
model id that was asked for.

| Provider | Model | Structured | Latency | Role |
| --- | --- | --- | --- | --- |
| Groq | `openai/gpt-oss-120b` | `json_schema` | 0.8s | **generator** |
| Cloudflare | `@cf/zai-org/glm-4.7-flash` | `json_schema` | 2–3s smoke | **auditor** |
| Gemini | `gemini-3.7-flash` | `json_schema` | 3.9s | **fallback** |
| Cloudflare | `@cf/nvidia/nemotron-3-120b-a12b` | `json_schema` | 2.0s smoke | auditor, costly |
| Cloudflare | `@cf/google/gemma-4-26b-a4b-it` | `json_schema` | 2.5s smoke | not viable — see below |
| NVIDIA | `nvidia/nemotron-3-super-120b-a12b` | `json_schema` | 0.7s | **benchmark only** |

Catalogue endpoints used for discovery, all of which are the provider's own:

- Groq — `GET https://api.groq.com/openai/v1/models`
- Cloudflare — `GET /client/v4/accounts/{account}/ai/models/search`
- Gemini — `GET https://generativelanguage.googleapis.com/v1beta/models`
- NVIDIA — `GET https://integrate.api.nvidia.com/v1/models`

## The limits that actually shape the design

These came out of live calls and are the reason the route is what it is.

### Groq: 8,000 tokens per minute, and `max_tokens` counts against it

Measured from Groq's own `x-ratelimit-*` headers on a real call:

```
x-ratelimit-limit-tokens      8000
x-ratelimit-remaining-tokens  4771     after one 1,181-token request
x-ratelimit-reset-tokens      24.2s
x-ratelimit-limit-requests    1000
```

The reservation is the part worth knowing: a request declaring
`max_tokens: 2048` with a 1,181-token prompt consumed **3,229** of the 8,000,
not 1,181. The budget is charged on what a call *might* use.

Two consequences:

- **Groq can generate.** One entry draft is 1,181 in / 477 out — comfortably
  inside a minute's budget, several times over.
- **Groq cannot audit.** An eight-item audit batch is ~4,800 input tokens, and
  with an output allowance it asks for more than 8,000 in one request. Groq
  refuses it outright with `HTTP 413 … on tokens per minute (TPM): Limit 8000,
  Requested 13477`. Not a quota that recovers in a minute — a single request
  that does not fit.

Keeping `max_output_tokens` tight on the generator directly buys throughput.

### Cloudflare: a daily Neuron allowance, and the meter is on every response

Workers AI returns `usage.neurons` per call, so the engine reads it rather than
inferring it from a price list — `Completion.usage_units` carries it.

Measured on one representative eight-item audit batch (synthetic prose, 20,783
characters of prompt), extrapolated to the 13 batches a 100-item book needs:

| Model | in | out | neurons/batch | per 100-item book |
| --- | --- | --- | --- | --- |
| `@cf/zai-org/glm-4.7-flash` | 4,785 | 4,275 | 181.9 | **2,365** |
| `@cf/nvidia/nemotron-3-120b-a12b` | 4,793 | 3,537 | 696.7 | **9,057** |
| `@cf/google/gemma-4-26b-a4b-it` | 3,185 | 4,096 | 140.7 (4 items) | ~3,500, and see below |

Against the Free plan's 10,000 Neurons/day, that is roughly **24%** of a day for
GLM and **91%** for Nemotron. Nemotron would leave no room for the replacements
a run actually makes, let alone a second run the same day.

Gemma 4 26B could not do an eight-item batch at all: it exhausts its output
budget on reasoning tokens and returns `finish_reason: length` with empty
content, at 4,096 and again at 16,384. Halving the batch to four made it answer
— and it still finished at exactly 4,096 output tokens, which is the ceiling
rather than a stopping point. It answers a trivial smoke request in 2.5s, so
this is a workload limit rather than a broken model, but an auditor that needs
its batch halved and is still at its ceiling is not one to depend on.

GLM's own numbers moved between runs — 181.9 Neurons on one batch, 211.9 on
another with a larger output ceiling — which is what a reasoning model does.
Budget around 200 per batch rather than the lower figure.

### Gemini: free tier, and a busy one

`gemini-3.7-flash` answers structured requests correctly. It also returned
`HTTP 503 — This model is currently experiencing high demand` on an
audit-shaped call during this pass, which is why it is a fallback rather than a
primary. The chain treats 503 as retryable, which is the right handling.

Free-tier quotas are per project and are not exposed on the API response; read
them in AI Studio. Billing was not enabled for this pass and must not be.

### NVIDIA: works, and is not in the route

`nvidia/nemotron-3-super-120b-a12b` answered in 0.7s with valid structured
output — the hosted twin of the Cloudflare Nemotron, which makes it a useful
control when the auditor gold test runs.

It stays in `llm.benchmark`, which nothing routes a workbook through, because
whether the hosted free tier permits routine commercial use has not been
established. That is a question for whoever owns the account, not an
engineering conclusion.

## Data use — read before the first workbook is sold

Recorded from each provider's own current documentation, as pointers to check
rather than conclusions. All four differ from each other, and several differ
between their free and paid service.

| Provider | What to confirm | Where |
| --- | --- | --- |
| Groq | Retention and training use on the free tier; whether commercial use of the free tier is permitted | groq.com terms / privacy |
| Cloudflare | Workers AI data handling; Free plan terms | cloudflare.com Workers AI docs |
| Gemini | **Free tier and paid tier have different data-use posture.** Confirm whether free-tier content may be used to improve products | ai.google.dev terms |
| NVIDIA | Whether the hosted free/trial tier permits routine commercial use at all | build.nvidia.com terms |

What the engine does to limit exposure, regardless: no PDF is ever uploaded, and
the only book text that leaves the machine is one example sentence per candidate
word plus the paragraphs immediately around a chosen excerpt, capped at
`CONTEXT_CHARACTER_LIMIT` per request.

## Zero cost is a configuration property, not a hope

`ProviderConfig.cost` is a declaration this deployment makes about an endpoint,
and `LLMConfig` refuses to load a job with a `paid` endpoint anywhere in the
generating route — generator, auditor, or fallbacks. A paid endpoint may only be
named under `llm.benchmark`, which `build_chains` does not read.

Nothing here inspects an account or a card, and nothing could. The point is
narrower and worth stating: the way "a workbook costs nothing" dies is not a
decision, it is a fallback added on a bad afternoon by somebody who needed a run
to finish. That edit now fails to load.

An exhausted free quota surfaces as a provider failure, so the chain falls back
to another free endpoint or the run stops. It never starts spending.
