# Running this against a real book for the first time

Everything in `tests/` runs against PDFs this repository renders itself. Those
fixtures are real PDFs — running heads, folios, first-line indents, words broken
across lines, curly quotes — and they are still books written to be parseable by
the parser that parses them. A published novel was typeset by somebody who had
never heard of this engine.

So the first real book is not a formality, and "the parser did not crash" is not
the same as "the chapter map is right". This is what to do instead.

## Before anything

The PDF goes in `bookengine/sources/`, which is gitignored. A book is never
committed, never pushed, and never uploaded whole to a model provider — the only
book text that leaves the machine is one example sentence per candidate word and
the paragraphs immediately around a chosen excerpt. Generated output lands in
`bookengine/output/`, also gitignored, because it contains excerpts.

## 1. Ingest, and read what it says

```
bookengine ingest --book sources/the-maze-runner.pdf
```

No model is called and nothing is generated. What comes back is the report you
have to actually read:

| Line | What you are checking |
| --- | --- |
| PDF hash | Identifies the exact file. Every locator in the run belongs to it. |
| Pages | Matches the book. |
| Detected chapters | **Against the contents page, not against what you expect.** |
| Chapter detection pass | `page furniture removed` is the ordinary path. |
| The chapter listing | Page ranges that climb steadily and lengths in the same order of magnitude. |
| Running heads removed | Non-zero for almost any published novel. |
| Words rejoined across lines | Plus how many the book could not confirm. |
| Ingestion status | `PASS` or `REVIEW_REQUIRED`. |

Paragraphs are worth a second look on a new book. If the report names any over
5,000 characters, paragraph assembly has merged blocks a reader sees as
separate — usually a page or scene break it could not detect. Excerpts are
still cut at sentence boundaries inside such a block, so nothing wrong is
quoted, but "the passage around this excerpt" is then the wrong passage.

A chapter map that looks suspicious is `REVIEW_REQUIRED`, and `vocab` refuses to
run against it until a person says otherwise. That is the whole point of the
status: chapter assignment is the one thing in a workbook that nothing
downstream can check. Every quotation can be real, every word can occur where it
says, and the whole book can still be filed one chapter off.

Once the count is confirmed, put it in the job file as `expected_chapters` and
re-run. A mismatch is then a refusal rather than a warning — which is what
catches a prologue detected as chapter 1, or an epilogue as chapter 63.

## 2. Check the text by hand, in five places

The report gives you aggregates. These are the places where a parser assumption
that no fixture exposed tends to show up. `--ingest-only` on the `vocab` command
prints the same report against the job's book, or read `chapter.text` directly:

```python
from bookengine.source.ingest import ingest_book
document = ingest_book("sources/the-maze-runner.pdf").document
print(document.chapter(1).text[:600])
```

1. **The opening of chapter 1.** Does it start at the first sentence of the
   chapter, or does it carry the heading, a part title, or an epigraph?
2. **Three chapters from the middle.** Read a paragraph. Is it a paragraph?
3. **The last chapter.** Does it end where the story ends, or does it run into
   the acknowledgements?
4. **A chapter transition.** Print the last 300 characters of one chapter and
   the first 300 of the next. Nothing from the second should be in the first.
5. **A page boundary inside a paragraph.** Find a paragraph whose `page_start`
   and `page_end` differ and read across the join. No running head, no folio, no
   missing space, no swallowed word.

Then the repairs specifically:

```python
for chapter in document.chapters:
    for paragraph in chapter.paragraphs:
        for offset in paragraph.uncertain_repair_offsets:
            start = paragraph.char_start + offset
            print(chapter.number, repr(chapter.text[start - 40 : start + 40]))
```

These are the words the engine rejoined across a line ending and could not
confirm against the rest of the book. No excerpt is drawn through one, so they
cannot reach a workbook — but if there are a great many, the pool of usable
passages is smaller than it looks, and reading a few tells you whether the
hyphen decision is behaving on this typesetter's work.

## 3. Smoke-test the providers

```
bookengine smoke --config configs/the-maze-runner.yaml
```

One tiny request per endpoint. It reports which keys work, which model ids still
exist, which endpoints honour a schema, what a rate limit looks like, and
whether a provider quietly substituted a different model. Run it before a book,
not during one: a generation run reaches its first audit batch after an
ingestion and a hundred model calls.

If only one provider answers and `llm.audit.requirement` is `provider`, the
smoke report says so. Every row would then be written and audited by the same
endpoint, and with the default `on_shared: needs_review` none of them would be
exported as proved.

## 4. Generate one lesson before generating five

Cut the job down to `lesson: 1` and run it. A hundred items is five times the
cost of finding out the same thing.

Read the output as a tutor would: open `vocabulary.tsv`, check ten excerpts
against the book, check that the Korean is Korean and the chapter numbers are
right. Then read `audit.json` — particularly the rejected candidates, which are
where a bad prompt shows itself.

## 5. Only then, the whole book

Do not raise `limits.provider_calls_per_candidate` to make a run finish — it is
a ceiling on what a misbehaving endpoint may spend, and reaching it is a
provider problem rather than a book problem.

Nothing else in the job file can help, which is deliberate. `excerpt.
unconfirmed_repairs` and `llm.audit` change what is *attempted* and what is
*reported*; neither can make an unproved quotation or an unreviewed row
exportable. If a run comes up short, `audit.json` says which lesson and why.
That is the thing to fix.

## What "free" needs someone to confirm

The engine is built to cost nothing per run and the provider list is
configuration, not code. Nobody has checked the terms, and this is a commercial
tutoring business, so before a production run somebody should confirm for each
provider actually used:

- whether the free tier permits commercial use;
- what the data retention policy is;
- whether submitted text may be used to train models;
- what the rate and volume limits actually are.

This matters more here than for a general tool because the text being submitted
is short excerpts of a copyrighted novel. It is a small amount, and it is not
nothing. This is a note to make the assumption explicit, not legal advice, and
it is not an engineering blocker — but it should be answered before the first
workbook built this way is sold.
