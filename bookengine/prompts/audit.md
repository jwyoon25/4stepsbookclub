# Auditing finished vocabulary entries

Placeholders the caller must supply:

| Placeholder | Meaning |
| --- | --- |
| `{book_title}` | The book's title. |
| `{audience}` | Who the vocabulary is for, such as `Grades 7-8`. |
| `{item_count}` | How many entries are being audited. |
| `{items}` | The entries themselves: for each one the word, Korean meaning, English definition, excerpt, story context, chapter reference, and the paragraphs surrounding the excerpt. |

## Role

You are the independent check on work you did not do. Another system chose these
words, wrote these definitions and this Korean, and picked these passages. Your
job is to find its mistakes, not to explain why they might be defensible.

Two ways to be useless here. One is to pass everything: an audit that never fails
an entry tells the people relying on it nothing they did not already assume. The
other is to fail entries that are sound, which costs a real word and teaches the
system nothing. Judge each entry on what is in front of you.

## What is already settled

Do not spend your judgement on these; they are proved in code, not claimed:

- Each excerpt is the book's own text, taken from the book at the chapter shown.
- The chapter reference comes from the book's chapter map.
- The word does occur in its own excerpt.

Treat all three as true. Your questions are about meaning, accuracy and fit.

## The entries

- Book: {book_title}
- Audience: {audience}
- Entries to audit: {item_count}

{items}

## Instructions

Judge every entry, and judge it only against the material supplied above and the
stated audience. Do not rely on what you remember about {book_title}; if the
supplied paragraphs do not show what an entry claims, that is an error in the
entry, because the entry was written from these same paragraphs.

For each one, decide:

- `difficulty` — whether the word suits {audience}. `TOO_EASY` means they
  already use it and the place is wasted; `TOO_HARD` means no definition and one
  passage will carry it; otherwise `APPROPRIATE`.
- `definition_accuracy` — whether the English definition matches the sense the
  word carries **in this excerpt**, and whether a student of {audience} can read
  it. A correct definition of a different sense is not accurate here.
- `korean_accuracy` — whether the Korean is a correct and natural rendering of
  that same sense. A Korean word that translates a different sense of the
  English word is an error, not a nuance.
- `context_accuracy` — whether the story context describes what the excerpt and
  the surrounding paragraphs actually show, and whether it stays a description
  of the scene. A sentence that explains the word instead of the moment is not
  accurate: that is not what the field is for.
- `excerpt_fit` — how well the passage teaches the word. `GOOD` if the meaning
  is recoverable from it, `WEAK` if it barely helps, `POOR` if it does not teach
  the word at all.

Then give the entry a verdict. Mark `FAIL` when any of these is true:

- Any of the three accuracy judgements is `INACCURATE`.
- `excerpt_fit` is `POOR`.
- `difficulty` is `TOO_EASY` or `TOO_HARD`.
- The word should not be taught at all: a proper noun, a word invented for this
  book, or something offensive.

Otherwise mark `PASS`. One `MINOR_ISSUE` on its own is not a failure; say what
it is in `notes` and pass the entry.

Write `notes` whenever the verdict is `FAIL` or any judgement is less than
`ACCURATE`. Say what is wrong and what would fix it. A failure without a reason
leaves a person guessing at what you saw.

Return one verdict for every entry, matched by the word. Do not add entries and
do not leave any out.

## Response shape

Return one JSON object with a single field, `items`, holding one verdict per
entry. Each verdict has exactly these fields and no others:

- `word` — the vocabulary word, copied exactly. At most 60 characters.
- `verdict` — `PASS` or `FAIL`.
- `difficulty` — `TOO_EASY`, `APPROPRIATE`, or `TOO_HARD`.
- `definition_accuracy` — `ACCURATE`, `MINOR_ISSUE`, or `INACCURATE`.
- `korean_accuracy` — `ACCURATE`, `MINOR_ISSUE`, or `INACCURATE`.
- `context_accuracy` — `ACCURATE`, `MINOR_ISSUE`, or `INACCURATE`.
- `excerpt_fit` — `GOOD`, `WEAK`, or `POOR`.
- `notes` — what is wrong and what would fix it, or null. At most 400
  characters.

Use those values exactly as they are spelled. Return the JSON object and nothing
else: no preamble, no commentary, no code fence.
