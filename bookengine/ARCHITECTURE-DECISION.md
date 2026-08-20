# Book Engine Architecture Decision

- **Status:** Accepted for V1
- **Decision date:** 2026-08-20
- **Scope:** Book ingestion, source verification, and vocabulary generation

This records the decisions taken while building the first version, and the
reasoning behind the ones that were close. It complements
[`CONTENT-WORKFLOW-DECISIONS.md`](../workbooks/CONTENT-WORKFLOW-DECISIONS.md),
which is founder-locked and which this engine treats as a fixed target rather
than something to negotiate with.

## Python, not Node

The rest of this monorepo is Node ESM, and the first recommendation made during
this session was to stay there: `pdfjs-dist` and `ajv` are already dependencies,
`node --test` is already the runner, and the output has to become JSON that Node
code consumes. Uniformity is worth something.

**Decided against, by the founder, and the reasoning holds.** The trajectory of
this component runs through lemmatization, local model inference, embeddings,
document analysis and evaluation, and Python has the better ecosystem for every
one of them. Choosing Node would win a small amount of consistency now and lose
repeatedly later. The precedent for a non-npm toolchain already exists here: the
`workbook:*` scripts shell out to the Typst CLI.

The integration question is explicitly **not** decided. This is a CLI that writes
files. When an employee-facing UI arrives, a Node app invoking it as a worker, a
FastAPI wrapper, and porting a stable piece are all still open. Nothing here
forecloses any of them, and nothing here is a server.

## `bookengine/`, a sibling of `workbooks/`

`workbooks/` is content-in, PDF-out. This is PDF-in, content-out. They are
different jobs with different toolchains and they meet at two files:

- `workbooks/schema/lesson.schema.json` — the entry shape and its length limits
- `workbooks/builder/browser/sheet-contract.mjs` — the Vocabulary tab's columns

Those are mirrored as Python constants in `export/workbook_contract.py` rather
than parsed at runtime, so the engine works on a machine with the package and no
monorepo checkout. A test opens both originals and asserts the copies still
agree. The alternative — discovering drift when a tutor pastes a run into the
Sheet and is told column 5 is misnamed — is much worse than a failing test.

## The excerpt is a locator, not a string

This is the decision the whole design turns on.

The obvious arrangement has a model return a quotation and code check it against
the book. That works, and it means the system's correctness depends on a check
being present at every point where a quotation could enter.

The arrangement built instead gives a model no way to return a quotation. It
sees a numbered list of passages and returns an integer. An excerpt is
`ExcerptLocator(chapter, char_start, char_end)`, and its text is produced only by
`resolve_excerpt`, which slices the chapter. There is no field in
`vocabulary/schemas.py` that could carry quote text — the pydantic models use
`extra="forbid"`, so a model volunteering one is refused rather than
half-accepted.

Verification still runs, and deliberately runs twice by two independent routes:
`slice_matches` trusts the offsets and re-cuts, `present_in_chapter` ignores the
offsets entirely and searches the chapter. They can only disagree if something
corrupted a locator, which is exactly the case a single check would miss.

The same reasoning governs chapter references. `Chapter 17` is a property of the
locator. A model saying "this is from Chapter 14" has nowhere to say it.

## `READY` has one door

`VocabularyItem.mark_ready` is the only way to reach `READY`, and it refuses
without a passed verification, a locator, an excerpt, and a passed audit.
`transition()` raises if asked for `READY` directly. So "a hallucinated quotation
cannot become a trusted row" is enforced by a function signature rather than by a
review step that could be forgotten.

## The candidate pool is harvested, not recalled

The brief describes generating 40–60 candidates per lesson by asking a model.
The default here inverts that: `vocabulary/harvest.py` takes every word type out
of the lesson's own chapters, drops what no vocabulary list contains, ranks by
rarity, and the model scores the survivors.

Three reasons. Every candidate provably occurs in the reading, so the commonest
failure of the model-led arrangement — a plausible word that is not in the book —
does not need catching because it cannot happen. Only a word list with one
example sentence each leaves the machine, rather than several chapters of a
copyrighted novel. And the model spends its attention on whether a Grade 8
student should learn `predicament`, which is the part it is good at.

The proper-noun filter inside the harvester is worth noting because the first
version of it was wrong. Position was the obvious signal — a capital where the
grammar does not license one — and it fails on `Mr. Alder` and `Dr. Vance`, whose
capitals follow a full stop and look exactly like the start of a sentence. The
decisive signal is simpler: a common noun appears in lower case *somewhere* in a
novel and a name never does. Position survives as the tie-breaker for words that
appear once or twice.

The model-led mode is still there as `candidates.mode: model`, filtered through
the same occurrence check, because a word-type harvest cannot see a phrase and a
book with unusual vocabulary may defeat the ranking. It is a setting, not a
rewrite.

## Word families are a setting, not a decision

Whether `run`, `running` and `ran` are one vocabulary entry is a teaching
question. `dedupe.policy` decides it and defaults to `lemma`. Exact normalized
duplicates are blocked across the whole book under every policy, because two
rows with the same word on them is a defect whatever anyone thinks about word
families.

The rule-based lemmatizer that ships in the core handles plurals, past tense and
participles, and deliberately does **not** handle comparatives or adverbs. It
was going to: stripping `-er` turns `corner` into `corn`, which would silently
merge two unrelated words and drop one from the book. Silently merging is worse
than not merging, so those inflections are reached only when the optional
`lemminflect` extra is installed, and every run records which lemmatizer it used.

## Hyphen repair is decided by the book, and what it cannot decide is not quoted

A justified book breaks `incomprehensible` across a line, and without rejoining
it the word is in the book but not findable in it. Rejoining is therefore
necessary and locally undecidable: `extraor-` + `dinary` and `self-` +
`conscious` look identical at the break, and closing up the second invents a
spelling no English book contains.

It is not undecidable globally. A novel that writes `self-conscious` sets it
whole somewhere else and never writes `selfconscious`. So both reconstructions
are looked up in a lexicon of every word the book sets complete on one line, and
the attested one wins. That is the same principle as everything else here: the
source document is the authority, and the engine's job is to ask it rather than
to guess well.

Where the book attests both forms or neither, the repair is recorded as
uncertain, and no excerpt is drawn through one. Preferring passages without them
would not be enough — a word with one usable occurrence would still be quoted
through a spelling nobody can prove. `excerpt.allow_uncertain_repairs` is the
deliberate way out for a book hyphenated past usefulness, and the ingestion
report says how much of the book the bar is costing.

## Page furniture is labelled, not deleted

Running heads are stripped before chapter detection, because a title repeated
three hundred times otherwise looks like the most dependable heading in the
book. But some books set their chapter headings in the same margin band, and for
those the strip takes the headings too and the book reads as chapterless — so
detection retries over the whole line stream.

The two needs are opposite: detection sometimes wants the furniture, quoting
never does. So the furniture is marked on the line rather than removed from the
list. Detection reads everything and its heading indices stay valid; paragraph
assembly reads only the prose. Neither pass can put `THE MAZE RUNNER 143` in a
student's excerpt.

## A lesson is filled before the next one starts

Lessons are built in order, and each claims its vocabulary from a registry the
next one then has to work around. That guarantees uniqueness cheaply, and it
costs something real: if `reluctant` is a strong candidate in lessons 1 and 4,
lesson 1 takes it whether or not lesson 4 had anything else as good.

Accepted for now, because the alternative — building every lesson's pool first,
measuring the collisions, and allocating globally — is an optimisation over
educational quality, and there is no evidence yet about how often it matters.
The engine does not foreclose it: `build_pool` and `build_lesson` are separate,
the registry is passed in rather than owned, and `conflicts_among` can judge any
proposed allocation. A global allocator would sit between them without either
changing.

What would settle it is a real book. `audit.json` records every candidate pool,
so a first Maze Runner run says how many strong candidates two lessons actually
compete for.

## Refusing is a feature, and the confidence model has three tiers

Chapter detection reports `high`, `acceptable` or `low`. Blockers — no headings,
fewer than two, two heading styles that explain the book equally well — cannot be
cleared by anything. Warnings, such as chapters that do not start on a fresh
page, can be cleared by `book.expected_chapters`, and only by that: it is the one
fact about a book the PDF cannot supply about itself, and requiring a human to
supply it is the point.

Between those and success sits the third tier. A chapter map can parse cleanly
and still look wrong in a way only somebody holding the book can settle — a
chapter of thirty-seven characters is usually a heading matched inside the
prose, and every quotation filed under it would be real and misattributed.
Ingestion reports `REVIEW_REQUIRED` for those and `vocab` refuses to run.

The way past is a person, and the approval is kept so they are only asked once
per book. What is approved is the chapter map rather than the file: the record
carries a fingerprint of every chapter's number, heading, pages and length, so a
change to the ingester invalidates the approvals it would have altered. A file
hash alone would let a new parser inherit confidence earned by the old one.

## Configuration is YAML, validated by pydantic

The monorepo's convention is JSON with JSON Schema and `ajv`, and that was the
initial recommendation. Since the engine is Python, pydantic is already present
for the model-response boundary and YAML is the friendlier format for a file a
person writes by hand — it takes comments, and `configs/example.yaml` uses them
to document every default. The JSON-Schema convention is preserved where it
actually matters: the *content* contract is still `lesson.schema.json`, and this
engine is held to it.

## Providers are configuration

No module outside `llm/registry.py` knows a provider's name. Model identifiers
come from the environment, because a free provider's catalogue is the single
thing most certain to go stale. Any endpoint speaking the OpenAI shape works
with a `base_url` in the job file and no code change.

Generator and auditor get separate chains that share the fallback list, which
creates the case worth naming: both primaries down, both chains on the same
fallback, one model writing and marking every row while the job file still names
two providers. So independence is computed from the completions that came back
rather than from the configuration, at three levels — two providers, two models
on one provider, or neither — and a run claims the weakest level any exported
row reached. `llm.audit.requirement` sets the bar and `llm.audit.on_shared` says
what happens to rows below it; the default keeps the work and refuses to call it
proved.

## Deferred

- **OCR.** V1 refuses image-only scans by name.
- **A web UI.** The CLI writes files; a UI reads them.
- **Google Sheets API.** The TSV is pasted by a person, which needs no
  credentials and no OAuth scope.
- **Other book-derived content.** `source/` was kept free of any mention of
  vocabulary so that comprehension questions and lesson summaries can reuse it.
  Nothing has been built for them, and nothing should be until there is a second
  real consumer to design against.
