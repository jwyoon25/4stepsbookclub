# Providers

Model ids and free allowances move faster than anything else in this engine, so
this file records what was **confirmed live on 2026-08-23** rather than what
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
| Mistral | `mistral-large-2512` | `json_schema` | 1.1–22.0s by stage | **generator** |
| Groq | `openai/gpt-oss-120b` | `json_schema` | 0.8s | **fallback** |
| Cloudflare | `@cf/zai-org/glm-4.7-flash` | `json_schema` | 2–3s smoke | **auditor** |
| Gemini | `gemini-3.7-flash` | `json_schema` | 3.9s | **fallback** |
| Cloudflare | `@cf/nvidia/nemotron-3-120b-a12b` | `json_schema` | 2.0s smoke | auditor, costly |
| Cloudflare | `@cf/google/gemma-4-26b-a4b-it` | `json_schema` | 2.5s smoke | not viable — see below |
| NVIDIA | `nvidia/nemotron-3-super-120b-a12b` | `json_schema` | 0.7s | **benchmark only** |

Catalogue endpoints used for discovery, all of which are the provider's own:

- Groq — `GET https://api.groq.com/openai/v1/models`
- Mistral — `GET https://api.mistral.ai/v1/models`
- Cloudflare — `GET /client/v4/accounts/{account}/ai/models/search`
- Gemini — `GET https://generativelanguage.googleapis.com/v1beta/models`
- NVIDIA — `GET https://integrate.api.nvidia.com/v1/models`

## The limits that actually shape the design

These came out of live calls and are the reason the route is what it is.

### Mistral: enough tokens, with request rate as the pacing constraint

`mistral-large-2512` appeared in this account's live `/v1/models` catalogue on
2026-08-23 with a 262,144-token context and no deprecation flag. The requested
model id and the model id returned by every completion were both exactly
`mistral-large-2512`; there was no silent alias or substitution.

The existing OpenAI-compatible adapter worked without a provider-specific
branch. One tiny structured smoke call and seven synthetic generator-stage
calls all used native `json_schema`, passed local Pydantic validation, and
finished with `finish_reason: stop`:

| Stage | runs | input | output | latency | result |
| --- | ---: | ---: | ---: | ---: | --- |
| smoke | 1 | 26 | 18 | 6.109s | schema and answer passed |
| rank 20 | 3 | 1,719 | 1,704–1,727 | 21.601–22.041s | all 20 terms returned |
| occurrence | 2 | 774 | 30–35 | 1.116–1.163s | valid source-list index |
| entry draft | 2 | 1,022 | 84–85 | 2.694–2.704s | schema passed |

Live response headers reported:

```
x-ratelimit-limit-tokens-minute  250000
x-ratelimit-limit-req-minute     4
```

That token rate is far above this workload. Four requests per minute — the
dashboard's rounded 0.07 requests/second — is the practical limit. Ranking
calls are slower than the 15-second request interval already; occurrence and
entry calls are not. The production profile therefore configures a 15.5-second
minimum interval between starts of every Mistral HTTP request. That monotonic,
provider-instance schedule is shared by ranking, occurrence, entry drafting,
structured-output fallback attempts, and retries. A normal sequential run
should budget about 12–15 minutes per 20-item lesson and 60–75 minutes per
five-lesson book, before replacement work. The generic chain classifies 429 as
retryable and honours the full `Retry-After`; it does not silently move to paid
capacity.

After proactive pacing was added, four tiny synthetic structured calls started
15.507s, 15.504s, and 15.518s apart. All four returned HTTP 200 from
`mistral-large-2512`, with no 429; together they used 60 input and 28 output
tokens in 47.393s. No book text was used.

Using the observed Lesson 1 request composition (13 ranking, 11 occurrence,
20 entry calls) and the measured Mistral token counts gives this estimate:

| Scope | input | output | standard API value | share of $10 allowance |
| --- | ---: | ---: | ---: | ---: |
| one lesson | ~51,301 | ~24,312 | **~$0.062** | ~0.62% |
| five lessons | ~256,505 | ~121,561 | **~$0.311** | ~3.11% |

The value uses Mistral's [current published standard price for Mistral Large
3](https://docs.mistral.ai/inference/pricing): $0.50 per million input tokens
and $1.50 per million output tokens. It implies
about **32 five-lesson books** per $10 allowance if real books resemble this
fixture and there are no replacements. These are planning estimates, not a
promise about model output length or future pricing.

This deployment marks Mistral `cost: free` only because the account owner
confirmed Free mode, a $10 included monthly API allowance, current usage of $0,
and pay-as-you-go disabled. That is an operational property of this account,
not a universal property of Mistral's API. Paid overage must remain disabled;
an exhausted allowance is expected to surface as a provider failure.

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
| Mistral | Free-mode Studio/API input and output may be used for model improvement unless the account opts out; confirm the Admin privacy toggle, retention, and the commercial terms that apply to this deployment | [data controls](https://help.mistral.ai/en/articles/455207-can-i-opt-out-of-my-input-or-output-data-being-used-for-training) / [terms](https://legal.mistral.ai/terms) |
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

For Mistral specifically, `cost: free` means this account's included allowance
is the only spendable balance and paid overage is disabled. The application
cannot verify either dashboard setting. The account owner must keep those
conditions true and re-check them when credentials, organization, or plan
change.

An exhausted free quota surfaces as a provider failure, so the chain falls back
to another free endpoint or the run stops. It never starts spending.
