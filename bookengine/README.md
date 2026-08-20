# 4steps Book Engine

Turns a book PDF into vocabulary rows a tutor can paste straight into the
workbook's Google Sheet — and refuses to produce them when it cannot prove they
are right.

The engine is the deterministic half of the workbook pipeline. `../workbooks/`
takes validated content and makes PDFs from it; this takes a book and makes
validated content. They meet at the Vocabulary tab's nine columns and at
`workbooks/schema/lesson.schema.json`.

## The one idea

> **LLMs propose. Source text proves.**

A model is asked which words are worth teaching, which passage teaches one best,
what a word means in the sense used here, and whether another model's work is
any good. Those are judgements and a model is the right tool for them.

Everything factual is code. Which chapter a passage is in, what the book
actually says, whether a word occurs in a lesson's reading, whether two rows are
the same word — none of that is asked of a model, and a model's opinion about
any of it carries no weight anywhere in the engine.

The sharp end of this is quotations. An excerpt is not a string a model returned
and something later checked. It is a *locator* — a chapter and a pair of
character offsets — and the text is whatever slicing the chapter at those offsets
returns:

```python
quote = chapter.text[locator.char_start : locator.char_end]
```

A model choosing a passage returns an integer index into a list this engine
built. There is no field anywhere in `vocabulary/schemas.py` into which a model
could put quotation text or a chapter number. A fabricated quotation is not
detected; it is unrepresentable.

`READY` is reached through exactly one function, `VocabularyItem.mark_ready`,
which refuses without a passed verification, a source locator, and a passed
independent audit in hand. Only `READY` rows are exported.

## Setting it up

Python 3.11 or newer. From this directory:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

`uv sync` works too, if you have it; the `pyproject.toml` is standard PEP 621.

Two optional extras:

```bash
.venv/bin/pip install -e ".[lemma]"   # accurate word-family matching
.venv/bin/pip install -e ".[local]"   # Apple Silicon local inference
```

Without `[lemma]`, word families are matched by conservative suffix rules that
handle plurals, past tense and participles but not irregulars — `saw` and `see`
stay separate entries. Every run records which lemmatizer it used, so a workbook
built without the extra says so rather than implying a check it did not do.

## Running it

Ingest a book first. This asks no model anything and costs nothing, and it is
the fastest way to find out whether a PDF is usable at all:

```bash
.venv/bin/bookengine ingest --book sources/the-maze-runner.pdf --expected-chapters 62
```

```text
Book............................ the-maze-runner.pdf
Pages........................... 384
Detected chapters............... 62  (style: chapter-arabic, confidence: high)
Chapter 1   pages 1-7           3,912 characters
...
Running heads removed........... 748 lines ("THE MAZE RUNNER", "#")
Words rejoined across lines..... 191 (12 unconfirmed)
Paragraphs / sentences.......... 4,102 / 11,884
Ingestion status................ PASS
```

A book whose chapter map looks wrong in a way only a person can settle comes
back `REVIEW_REQUIRED` instead, with the reasons listed, and `vocab` refuses to
run against it. Read the chapter listing against the book, then record that you
have:

```bash
.venv/bin/bookengine ingest --book sources/the-maze-runner.pdf --approve
```

The approval is kept per book and covers that exact chapter map, so the same
PDF is not queried again — and a change to the ingester that would alter the map
asks again.

Then check the endpoints, which costs one tiny request each:

```bash
.venv/bin/bookengine smoke --config configs/the-maze-runner.yaml
```

Then write a job and run it:

```bash
.venv/bin/bookengine vocab --config configs/the-maze-runner.yaml
```

`configs/example.yaml` documents every setting with its default. The short
version is: a book, an audience, a list of lessons with chapter ranges, and how
many words each lesson needs.

From the repository root the same two commands are wired as npm scripts, next to
the workbook ones:

```bash
npm run book:ingest -- --book bookengine/sources/the-maze-runner.pdf
npm run book:vocab  -- --config bookengine/configs/the-maze-runner.yaml
npm run book:test
```

## What comes out

```text
output/the-maze-runner/
  vocabulary.tsv     the paste block
  vocabulary.json    every item, including the ones that failed, with provenance
  audit.json         the run's summary and per-check counts
```

The TSV's columns are the Vocabulary tab's columns, in its order, with its
wording, and it carries no header row: the tab's headings are already in row 4,
so the first line of the file is vocabulary item 1. Select the tab, click `A5`,
paste once. (`output.include_header: true` adds one, for a file somebody will
open on its own.)

`vocabulary.json` is the debugging artifact. Every item carries the sentence IDs
its excerpt came from, the page range, how many occurrences the word had, which
model wrote its definition, which model audited it, every status it passed
through and why, and — for items that did not make it — what rejected them.

## When it refuses

Refusing is a feature and there are four places it happens.

**An unusable PDF.** An image-only scan extracts as a handful of stray
characters, and a quotation "verified" against that is verified against nothing.
V1 does not do OCR and says so rather than guessing.

**An uncertain chapter map.** A wrong chapter map is the worst failure available
here: every quotation is real, every word occurs, and every row carries a chapter
number that is off by one for the whole book. Nothing downstream can catch it.
So detection reports a confidence, and a book that is merely unusual — chapters
that run on without a page break, say — needs `expected_chapters` in the job
before it will run. That count is the one fact about a book the PDF cannot supply
about itself.

**A lesson plan that does not fit.** Checked against the chapters the book
actually has, with the missing ones named.

**A chapter map nobody has checked.** Separate from detection failing outright.
A map that parsed but looks wrong — a chapter of thirty-seven characters, a
book that only produced headings once the running heads were put back — is
`REVIEW_REQUIRED`, and generation stops until somebody has run
`ingest --approve` against it.

**An audit that was not independent.** Both provider chains fall back to the
same list, so a job naming two providers can end up with one writing and
marking every row. Independence is measured from the completions that came
back, and rows that fall short of `llm.audit.requirement` are not exported as
proved. What happens to them is `llm.audit.on_shared`.

**A lesson that cannot be filled.** Twenty requested means twenty verified or a
failed run. Never nineteen and a success message.

```text
Lesson 3 could not reach 20 verified vocabulary items.
  17 items are READY.
  3 candidates were rejected.
    - 2 candidate(s): No usable passage for 'ordeal' in Chapters 25-36
    - 1 candidate(s): The independent audit rejected the Korean meaning (INACCURATE).
Generation was not marked successful. See audit.json.
```

Artifacts are still written on a failed run, so it can be inspected.

## Inference costs nothing

Nothing here depends on a paid API. Providers are named only in the job file:

```yaml
llm:
  generator:
    provider: groq
    model: ${GENERATOR_MODEL}
  auditor:
    provider: nvidia
    model: ${AUDITOR_MODEL}
  fallbacks:
    - provider: gemini
      model: ${GEMINI_MODEL}
```

Any endpoint speaking the OpenAI `/chat/completions` shape works with no code
change; unknown providers just need `base_url` and `api_key_env` in the job.
Gemini has its own adapter, and `mlx`/`local` points at a local `mlx_lm.server`
as the last link in the chain. Model identifiers live in the environment, never
in the job file, because a free provider's catalogue is the thing most certain to
go stale.

A chain retries a rate limit on the same provider with backoff, moves to the next
provider on a bad key, and when everything fails says what each one actually
said. Answers are cached by prompt hash, so a run that dies at lesson four does
not re-ask lesson one.

The generator and the auditor should be different providers. Independence is the
entire value of the audit stage, and a run where they are the same model says so
in its output and in `audit.json`.

## Books stay on this machine

Book PDFs go in `sources/`, which is gitignored, as are `output/`, `cache/` and
`.venv/`. Nothing commits a book.

The default `harvest` candidate mode exists partly for this reason: it takes the
candidate pool from the book's own text locally and sends a word list with one
example sentence each. The `model` mode sends chapters, which is why it is not
the default. In both modes, the only other book text that leaves the machine is
the passage being defined and the paragraphs immediately around it.

## Adding a provider

Most need no code. Put `base_url` and `api_key_env` in the job file and the
OpenAI-compatible adapter handles it. A provider with a different wire format
gets a module in `src/bookengine/llm/` implementing one method, and an entry in
`registry._SPECIAL_CASES`. `gemini.py` is the worked example.

## Tests

```bash
.venv/bin/pytest
```

295 tests, no network, no book PDFs, no API keys. Test books are real PDFs built
at test time by `tests/fixtures/synthetic_book.py` — with running heads, page
numbers, first-line indents, words hyphenated across line breaks and typographic
quotes — from prose written for this repository, so nothing copyrighted is
committed and extraction is genuinely exercised rather than mocked.

The tests that matter are the adversarial ones. `tests/fakes.py` is a model that
can be told to misbehave the way real ones do: fabricate a quotation, pick a
passage that does not exist, propose a word the book does not contain, return
malformed JSON, or approve nothing. `tests/test_pipeline.py` asserts that none of
it reaches a `READY` row. A suite that only ever saw good answers would pass
against a design with no verification in it.

`tests/test_source_fidelity.py` builds PDFs with specific typesetting defects in
them — a compound broken at its own hyphen, headings sharing a margin band with
the running head — and checks that neither an invented spelling nor a folio can
reach a quotation. `tests/test_smoke.py` runs the provider smoke test against a
local HTTP server, so status codes and error handling are exercised for real
with nothing hosted.

`tests/test_export.py` opens `workbooks/builder/browser/sheet-contract.mjs` and
`workbooks/schema/lesson.schema.json` and asserts this engine's mirrored copies
still agree with them. That is what would otherwise be discovered by a tutor
pasting a run into the Sheet and being told column 5 is misnamed.

## Project shape

```text
bookengine/
├── README.md
├── SKILL.md                  # how a coding agent should drive this
├── ARCHITECTURE-DECISION.md  # why it is built this way
├── pyproject.toml
├── FIRST-REAL-BOOK.md        # what to check before trusting a published novel
├── configs/example.yaml      # every setting, with its default
├── configs/the-maze-runner.yaml
├── prompts/                  # versioned prompt files
├── sources/                  # book PDFs (gitignored)
├── output/                   # runs (gitignored)
└── src/bookengine/
    ├── source/               # book-generic: nothing here mentions vocabulary
    │   ├── text.py           # the one definition of how text is compared
    │   ├── pdf.py            # extraction into positioned lines
    │   ├── layout.py         # running heads, paragraphs, hyphen repair
    │   ├── chapters.py       # detection, and refusing to guess
    │   ├── document.py       # chapters, paragraphs, sentences, offsets
    │   ├── excerpt.py        # locators, and how a quotation is proved
    │   ├── search.py         # occurrences and context windows
    │   ├── ingest.py         # orchestration, the report, PASS/REVIEW_REQUIRED
    │   ├── approval.py       # a person's word on a chapter map, kept per book
    │   └── cache.py
    ├── llm/                  # providers, chain, structured output, cache,
    │                         # and the smoke test
    ├── vocabulary/           # harvest, candidates, quotes, entries, audit,
    │   │                     # dedupe, verify, pipeline, models
    ├── export/               # TSV, artifacts, the Sheet contract
    ├── config.py
    ├── prompts.py
    └── cli.py
```

`source/` is deliberately free of any mention of vocabulary. Comprehension
questions, lesson summaries and analysis prompts all need exactly what it
provides — a book that can be quoted from and cited — and the point of the
boundary is that the next book-derived workflow does not rebuild it.

## Not built yet

No web UI, no queues, no database, no Google Sheets API, no OCR. The CLI is the
product for now; `ARCHITECTURE-DECISION.md` records what the UI would sit on top
of when it arrives.
