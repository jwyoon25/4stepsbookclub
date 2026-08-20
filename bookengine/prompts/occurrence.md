# Choosing which occurrence teaches the word

Placeholders the caller must supply:

| Placeholder | Meaning |
| --- | --- |
| `{book_title}` | The book's title. |
| `{audience}` | Who the vocabulary is for, such as `Grades 7-8`. |
| `{term}` | The vocabulary word. |
| `{sense}` | The sense it carries in this book. |
| `{occurrences}` | The numbered list of places the word occurs, one sentence per line, each line beginning with its number. |

## Role

You are choosing which of the book's own sentences will be printed in the
workbook beside the word {term}. The student sees that one passage and is asked
to learn the word from it, so the choice decides whether the entry teaches or
merely decorates.

## The occurrences

- Book: {book_title}
- Word: {term}
- Sense used in this book: {sense}
- Audience: {audience}

Every occurrence below was found in the book by the system, and the word is
already confirmed to be in each one. The numbers are the system's own and may
start at 0. Choose one of them.

{occurrences}

## Instructions

Judge each option on how well it would work on a workbook page, in this order:

1. **The meaning is recoverable.** A reader who did not know {term} should be
   able to get close to it from this sentence alone.
2. **It stands on its own.** Pronouns and references that need the previous page
   to make sense make a poor entry. So does a sentence that starts mid-thought.
3. **It gives nothing important away.** Avoid the sentence that reveals a death,
   a betrayal, or the ending. Students meet these entries beside the reading,
   not after it.
4. **It reads well out of context.** A moderate length, ordinary punctuation,
   and no long list of names.

The word being in the sentence is not a reason to prefer one option: that is
true of all of them.

You cannot supply a sentence. The field is a number, and the system cuts the
passage out of the book itself using the number you return, so the number is all
it needs.

If every option is poor, still choose the least poor one and say in `reason`
that none of them reads well. A person reads that note.

## Response shape

Return one JSON object with exactly these fields and no others:

- `index` — the number of the occurrence you chose, exactly as it is printed in
  the list above.
- `reason` — one short sentence on why that occurrence teaches the word best. At
  most 240 characters.

Return the JSON object and nothing else: no preamble, no commentary, no code
fence.
