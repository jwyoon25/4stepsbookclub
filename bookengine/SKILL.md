---
name: book-vocabulary
description: >
  Generate verified vocabulary workbook data from a book PDF for 4steps Book
  Club. Use when asked to make vocabulary for a book, fill a workbook's
  Vocabulary tab, or check whether a book PDF can be used at all.
---

# Generating vocabulary for a book

This skill drives `bookengine`, the verified book-content engine in this
monorepo. Its job is orchestration: preparing inputs, running the commands,
reading the result, and reporting honestly.

**It is not the verification.** Every factual guarantee — that a quotation is
the book's own words, that a chapter reference is real, that a word occurs in
its lesson's reading, that no word is taught twice, that each lesson has exactly
the requested number of items — is enforced in code, in
`src/bookengine/source/excerpt.py`, `src/bookengine/vocabulary/verify.py`, and
`src/bookengine/vocabulary/models.py`. Nothing you do here can strengthen those,
and nothing you are told here should ever be used to work around them.

## Absolute rules

1. **Never edit `vocabulary.tsv`, `vocabulary.json` or `audit.json` by hand.**
   They are the record of what was verified. Editing them makes the record a
   lie while leaving it looking authoritative.
2. **Never present a failed run as a success.** If the engine exits non-zero,
   say so and say which lesson came up short and why.
3. **Never supply a quotation, a chapter number, or a definition yourself**, and
   never fill a gap from your own knowledge of the book, from a summary, or from
   anything on the internet. If the engine could not produce an item, the answer
   is that it could not.
4. **Never commit a book PDF.** They belong in `bookengine/sources/`, which is
   gitignored.
5. **Never add `--no-cache` or edit a config to loosen a check** in order to get
   a run to pass. A refusal is the product working. No setting can make an
   unproved quotation or an unreviewed row exportable — that is enforced in
   code, not by convention — so a config change made for that reason will not
   work and will only obscure why the run came up short.
6. **Never run `ingest --approve` yourself.** It records that a *person* has
   checked a chapter map against the book. You have not got the book. Show the
   operator the report and the command, and let them run it.

## Where things go

| What | Where |
| --- | --- |
| Book PDF | `bookengine/sources/<the-book>.pdf` (gitignored) |
| Job configuration | `bookengine/configs/<the-book>.yaml` (committed) |
| Output | `bookengine/output/<the-book>/` (gitignored) |
| Reference config | `bookengine/configs/example.yaml` |

## The sequence

### 1. Ingest first, always

```bash
cd bookengine
.venv/bin/bookengine ingest --book sources/<the-book>.pdf
```

Read the report. Check the detected chapter count against the book's own
contents page. This costs nothing and asks no model anything, and it is how you
find out whether a book is usable before anything else happens.

If it refuses, stop. An image-only scan is not supported and an ambiguous
chapter map is not something to work around. Report what it said.

If the status is `REVIEW_REQUIRED`, stop and hand it to the operator. The
concerns are listed under "A person has to check these before generating", and
the answer to them is somebody reading the chapter listing against the book —
then running `ingest --book ... --approve` themselves. `vocab` will refuse until
they have. See `FIRST-REAL-BOOK.md` for what a first run against a published
novel needs beyond this.

### 1b. Smoke-test the endpoints

```bash
.venv/bin/bookengine smoke --config configs/<the-book>.yaml
```

One tiny request per endpoint, before a run rather than during one. It reports
which keys work, which model ids still exist, which endpoints honour a schema,
and whether the job's audit independence requirement can actually be met with
what is reachable today.

### 2. Write the job

Copy `configs/example.yaml`. You need, from the operator:

- the book PDF
- the student grade range
- the lesson boundaries as chapter ranges
- how many words per lesson (20 unless told otherwise)

Always set `book.expected_chapters` to the count you confirmed in step 1. It is
the check that catches a misread chapter map.

Ask the operator for anything you do not have. Do not invent lesson boundaries.

### 3. Check the plan before spending anything

```bash
.venv/bin/bookengine vocab --config configs/<the-book>.yaml --ingest-only
```

This validates the book and the lesson ranges and stops. It catches a lesson
pointing at a chapter the book does not have, which is the commonest mistake and
the one that would otherwise be found several minutes into a run.

### 4. Run it

```bash
.venv/bin/bookengine vocab --config configs/<the-book>.yaml
```

Needs API keys in the environment for whichever providers the job names — the
error message names the exact variable when one is missing. Takes minutes, not
seconds. `-v` shows per-lesson progress.

### 5. Read the result before reporting

| Exit code | Meaning | What to do |
| --- | --- | --- |
| 0 | Every lesson reached its target and every check passed | Report success, give the paste instruction |
| 1 | The run completed but did not meet its own bar | Report which lesson fell short and why; artifacts were still written |
| 2 | The job or the book is wrong | Report what needs fixing; nothing was generated |

On success, tell the operator:

- how many items, over how many lessons
- that quotations, chapter references and duplicates all passed
- what independence level the audit actually reached, if it is not `provider`
- where the TSV is
- to open the workbook's **Vocabulary** tab, click **A5**, and paste — the file
  has no header row, so the first line pasted is vocabulary item 1

On a shortfall, quote the engine's own explanation. It already names the lesson,
the count, and the reasons. Do not summarise it into "some items failed".

## Reading a shortfall

`audit.json` has the per-check counts and `vocabulary.json` has every rejected
item with its reason. The common causes, and the honest response to each:

| Reason | What it means | What actually helps |
| --- | --- | --- |
| No usable passage | Every occurrence is in a sentence outside the excerpt length limits, or one crossing a paragraph break | Widen `excerpt.max_sentences`, or accept fewer words |
| The audit rejected it | The second model found the definition, Korean, or context wrong | Nothing to do; it was replaced. Persistent failures suggest a weak auditor model |
| Candidate pool exhausted | The lesson's chapters do not hold enough teachable words | Raise `candidates.pool_size`, widen the chapter range, or lower `vocabulary_per_lesson` |
| Not scored | The model's reply omitted candidates | Usually a rate limit; re-run, since the cache makes it cheap |
| Audited by the endpoint that wrote it | Both chains fell back to one provider | Add a reachable endpoint to `llm.fallbacks` and re-run. No setting exports these rows, so changing `llm.audit` will not help |
| Stopped at its budget | An endpoint answered badly for a whole lesson | Read the rejection reasons first. It is a provider problem, not a book problem |

Raising `excerpt.max_characters` above 600 is not an option — that is the
workbook content schema's own limit and a longer excerpt is a row the builder
rejects.

## After a successful run

The TSV goes into the Vocabulary tab of a workbook copy made from the master
Sheet. The rest of the workbook workflow is unchanged and documented in
`workbooks/builder/RUNBOOK.md`. This engine produces one tab's content; it does
not run the workbook build.

## If you are asked to change the engine

Read `ARCHITECTURE-DECISION.md` first. The boundary that matters is that
`src/bookengine/source/` knows nothing about vocabulary — it is the layer a
comprehension-question or lesson-summary generator would reuse — and that
`READY` is reachable only through `VocabularyItem.mark_ready`. Run
`.venv/bin/pytest` and `.venv/bin/ruff check src/ tests/` before reporting a
change as done.
