# Prompts

Every instruction this engine gives a model lives here, in a file, rather than in
a string literal inside Python. The reason is who edits them: the wording of a
definition brief or an exclusion list is a teaching decision, and the person best
placed to improve it is not necessarily the person changing code. A prompt should
be readable, diffable, and safe for that person to edit.

`README.md` is documentation. The prompts are the five files named below.

## The five prompts

| File | Stage | Answer shape |
| --- | --- | --- |
| `candidates.md` | Propose words from a lesson's chapters | `CandidateList` |
| `ranking.md` | Score those words on the six rubric dimensions | `RankedList` |
| `occurrence.md` | Choose which occurrence of a word teaches it best | `OccurrenceChoice` |
| `entry.md` | Write the definition, the Korean meaning, and the story context | `EntryDraft` |
| `audit.md` | Judge the finished entries independently | `AuditReport` |

The answer shapes are pydantic models in
`src/bookengine/vocabulary/schemas.py`. A provider is given the matching JSON
schema from `json_schema_for(Model)`, so the shape is defined once. The
`Response shape` section of each prompt names the fields in prose for models that
follow instructions better than schemas; it is a description of the schema, never
a second source of truth for it.

## How a prompt is used

1. Read the file.
2. Replace each `{placeholder}` with the value the caller has.
3. Send it, with the schema for that stage, to the configured provider.
4. Validate the reply into the model. Anything that is not that shape is a
   `StructuredResponseError`, and the call is retried or falls through to the
   next provider.

**Substitution replaces only the markers listed at the top of each prompt.** No
other `{` or `}` appears in any prompt file, which keeps both possible
implementations safe — a plain `replace` per marker, or `str.format`. Keep it
that way when editing: if a prompt ever needs a literal brace, the loader has to
be looked at first. A marker left unreplaced should be treated as a bug in the
caller, not sent to a model.

## What the placeholders mean

Shared by several prompts:

| Placeholder | Meaning | Comes from |
| --- | --- | --- |
| `{book_title}` | The book's title | `BookConfig.title` |
| `{audience}` | Who the vocabulary is for, such as `Grades 7-8` | `AudienceConfig.label` |
| `{reading_range}` | The chapters a lesson covers | `LessonConfig.reading_range` |
| `{term}` | The vocabulary word | The candidate being worked on |
| `{sense}` | The sense that word carries in this book | `CandidateWord.sense` |

Per prompt:

| Prompt | Placeholder | Meaning |
| --- | --- | --- |
| `candidates.md` | `{lesson_number}` | The lesson number |
| | `{count}` | How many candidates to propose (`candidates_per_lesson`) |
| | `{excluded_terms}` | Words already taught or barred, one per line, or `(none)` |
| | `{source_text}` | The text of the lesson's chapters, from the `BookDocument` |
| `ranking.md` | `{candidates}` | The candidate words, one per line, each with its sense |
| `occurrence.md` | `{occurrences}` | The numbered occurrences, one sentence per line, numbered by `Occurrence.index` |
| `entry.md` | `{excerpt}` | The passage, cut from the book at its locator |
| | `{context}` | The paragraph containing it plus its neighbours, from `ContextWindow.as_prompt_block()` |
| `audit.md` | `{item_count}` | How many entries are being audited |
| | `{items}` | The finished entries, with the paragraphs surrounding each excerpt |

The numbering in `{occurrences}` must be `Occurrence.index` itself, and the
occurrence prompt says the numbers may start at 0. Renumbering the list for
presentation would silently move which sentence gets quoted.

## Editing a prompt cannot weaken the engine

This is the part worth being blunt about. The engine's guarantees are not
promises made in these files; a model that ignores every word here still cannot
put a fabricated quotation or a wrong chapter number into a workbook. The
guarantees are structural and live in code:

- **A model has no field for a quotation or a chapter.**
  `src/bookengine/vocabulary/schemas.py` defines every shape a reply may take.
  `OccurrenceChoice` carries an index into a list the engine built from the book.
  `EntryDraft` carries a definition, a Korean meaning and a story context, and
  nothing else. There is no field to put a sentence from the book into, so a
  fabricated quotation is not detected — it cannot be expressed.
- **A quotation is a locator, and the text is whatever the book says there.**
  `src/bookengine/source/excerpt.py` holds an `ExcerptLocator` — a chapter and a
  pair of character offsets — and `resolve_excerpt` is the only way to obtain the
  words. `verify_excerpt` then proves the exported text twice over: once by
  re-cutting the slice, and once by searching the chapter for the exported words
  without trusting the offsets at all.
- **The chapter reference is derived, never claimed.**
  `ExcerptLocator.chapter_reference` is the only place a chapter citation is
  produced. A model asserting "this is from Chapter 14" carries no weight
  anywhere in the engine, because nothing reads such an assertion.
- **A row cannot be published without that proof in hand.**
  `src/bookengine/vocabulary/models.py` has no transition into `READY`.
  `mark_ready` is the only route, and it refuses without a passed
  `ExcerptVerification`, a locator, an excerpt and a passed audit.
- **A proposed word that is not in the book is dropped.**
  `src/bookengine/source/search.py` finds occurrences in the source. A candidate
  the book does not contain in the lesson's chapters has no occurrences, so it
  has no locator and never reaches an entry.

What a prompt genuinely controls is quality: which words get proposed, how well
they are ranked, how clear a definition reads, how strict the audit is. Those are
worth iterating on. Nothing in this directory is load-bearing for whether the
workbook tells the truth.

## When editing

- Keep the `Response shape` section in step with the field names in
  `schemas.py`. The prompt is what the model reads; the schema is what the reply
  is validated against, and a prompt naming a field that no longer exists
  produces replies that are refused.
- `audit.md` spells out the allowed values for each judgement. They must match
  the `Literal` types in `schemas.py` exactly — `PASS`/`FAIL`,
  `TOO_EASY`/`APPROPRIATE`/`TOO_HARD`, `ACCURATE`/`MINOR_ISSUE`/`INACCURATE`,
  `GOOD`/`WEAK`/`POOR`.
- The character limits quoted in the prompts mirror the workbook's own content
  schema (`workbooks/schema/lesson.schema.json`) by way of the constants in
  `schemas.py`. Raising one in a prompt does not raise it anywhere else; it only
  produces answers the workbook builder rejects.
- If you add a placeholder, list it at the top of that prompt. That list is the
  contract the caller reads.
