# Scoring candidate words against the rubric

Placeholders the caller must supply:

| Placeholder | Meaning |
| --- | --- |
| `{book_title}` | The book's title. |
| `{audience}` | Who the vocabulary is for, such as `Grades 7-8`. |
| `{reading_range}` | The chapters the candidates were taken from. |
| `{candidates}` | The candidate words, one per line, each with the sense it carries in this book. |

## Role

You score candidate vocabulary words so that a lesson's limited places go to the
words that repay a student most. Someone else proposed this list; you are not
defending it. Scoring a weak word honestly low is the useful thing to do, because
the list is longer than the lesson needs and the lowest scores are dropped.

## The candidates

- Book: {book_title}
- Taken from: {reading_range}
- Audience: {audience}

{candidates}

## Instructions

Score every word you were given, including any you think should not be taught at
all. Do not leave a word out to signal disapproval — say so with a high
`exclusion_risk` instead. The system checks your list against the one it sent.

Each dimension is a whole number from 1 to 5.

- `difficulty` — how much of a stretch the word is for {audience}. 1 means they
  already use it; 5 means a demanding word that a definition and one good
  passage can still carry. A word beyond their reach is not a 5: score it low
  here and high on `exclusion_risk`.
- `general_utility` — how often the word repays them outside this book, in their
  own reading, writing and exams. 5 is very widely useful.
- `context_quality` — how well the book's own sentences make the meaning
  recoverable. 5 means an attentive reader could work it out from the passage.
- `educational_value` — how much is gained from studying this particular word: a
  useful root, a common word family, a precise idea they have no word for. 5 is
  high.
- `generality` — how far the sense travels beyond this scene. 5 is a general
  sense that works anywhere; 1 is tied to one moment, one idiom, or one use
  invented for this book.
- `exclusion_risk` — **a high number is bad here.** How likely it is that the
  word should not be taught at all: a proper noun or character name, a word
  invented for this book, narrow jargon, an archaic word with no present-day
  use, something offensive, or a word far beyond the audience. 1 means no
  concern; 5 means do not teach it.

Use the whole range. A list scored 4 and 5 throughout orders nothing and leaves
the choice to chance.

## Response shape

Return one JSON object with a single field, `ranked`, holding one entry per
candidate you were given. Each entry has exactly these fields and no others:

- `term` — the candidate word, copied exactly as it was given to you. At most 60
  characters.
- `difficulty` — whole number, 1 to 5.
- `general_utility` — whole number, 1 to 5.
- `context_quality` — whole number, 1 to 5.
- `educational_value` — whole number, 1 to 5.
- `generality` — whole number, 1 to 5.
- `exclusion_risk` — whole number, 1 to 5, where high is bad.
- `note` — anything a person should know about this score, or null. At most 400
  characters.

Return the JSON object and nothing else: no preamble, no commentary, no code
fence.
