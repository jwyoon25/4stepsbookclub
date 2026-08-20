# Proposing candidate vocabulary

Placeholders the caller must supply:

| Placeholder | Meaning |
| --- | --- |
| `{book_title}` | The book's title. |
| `{audience}` | Who the vocabulary is for, such as `Grades 7-8`. |
| `{lesson_number}` | The lesson these words belong to. |
| `{reading_range}` | The chapters this lesson covers, such as `Chapters 1-6`. |
| `{count}` | How many candidate words to propose. |
| `{excluded_terms}` | Words already taught or barred for this book, one per line, or `(none)`. |
| `{source_text}` | The text of those chapters. The only text words may be taken from. |

## Role

You choose vocabulary for a reading workbook. Students read the book in English
and study each word with a short English definition and a Korean meaning beside
it. You are proposing a longer list than the lesson will use, so that weak
candidates can be dropped later without leaving the lesson short.

## The reading

- Book: {book_title}
- Lesson: {lesson_number}, covering {reading_range}
- Audience: {audience}

Already taught or barred for this book, so do not propose them:

{excluded_terms}

The text of {reading_range} follows between the markers. It is the whole of
what you may work from.

--- BEGIN SOURCE TEXT ---
{source_text}
--- END SOURCE TEXT ---

## Instructions

Propose {count} words, best first, every one of them taken from the source text
above.

How the list is used, so that you can spend your places well: each word you
propose is looked for in the book by the system before anything else happens to
it. A word that does not occur in {reading_range} is discarded automatically.
Nothing is held against the rest of your list, but the place is gone. So a word
you half-remember from this book costs a place; a word you can see in the text
above does not.

Choose words that are worth a student's time:

- A genuine stretch for {audience} — not a word they already use, not one so far
  beyond them that a definition would not help.
- Useful outside this book, in their own reading and writing.
- Carrying a meaning here that the passage itself helps make clear.

Do not propose:

- Proper nouns of any kind: character names, place names, brands, titles.
- Words invented for this book, or slang that exists only inside its world.
- Highly specialised jargon that a general reader has no use for.
- Archaic words with no present-day value, even when the book uses them often.
- Words far below the audience, which fill a place without teaching anything.
- Two forms of the same word. Propose one of `hesitate` and `hesitation`.

Give the sense the word carries *in this book*. If a word is used here in an
unusual sense, that unusual sense is the one to describe.

Do not quote the book and do not name a chapter. There is no field for either,
and both are the system's own work.

## Response shape

Return one JSON object with a single field, `candidates`, holding {count}
entries. Each entry has exactly these fields and no others:

- `term` — the word alone, spelled as it appears in the text. At most 60
  characters.
- `reason` — one short sentence on why it is worth teaching. At most 240
  characters.
- `sense` — the meaning it carries in this book. A few words. At most 240
  characters.

Return the JSON object and nothing else: no preamble, no commentary, no code
fence. The exact shape is enforced by the system, and an unexpected field is
refused rather than ignored.
