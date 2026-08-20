"""Building the candidate pool out of the book, before any model is asked.

The obvious design is to hand a model a chapter and ask it for twenty words. It
has two problems. The model will name words that are not in the chapter, which
then have to be thrown away, and it means posting several chapters of a
copyrighted novel to a third party to discover words that are sitting in the
text already.

So the pool is harvested here instead: every word type in the lesson's chapters,
minus the ones no vocabulary list would ever contain, ranked by how likely it is
to be worth teaching. What the model receives is a word list with one example
sentence each, and what it does is the part that genuinely needs judgement —
deciding which of these a Grade 7 student should learn. Every candidate it sees
provably occurs in the lesson's chapters, because it came from them.

The proper-noun filter is the piece worth reading twice. Character and place
names are the single largest category of wrong vocabulary word, and they are
identifiable without a dictionary: a common noun is only capitalised where the
grammar licenses it, and a name is capitalised everywhere.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from ..source.document import BookDocument
from ..source.text import normalize_term

_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")

# Positions where a capital letter says nothing about the word: the start of a
# sentence, and the start of quoted speech.
_LICENSING_CHARACTERS = "\"'“‘([—-"

# Suffixes that mark the Latinate, academically portable vocabulary a workbook
# is usually reaching for. A weak signal, used only to break ties.
_ACADEMIC_SUFFIXES = (
    "tion", "sion", "ment", "ance", "ence", "ity", "ous", "ious", "able",
    "ible", "ate", "ive", "ful", "less", "ness", "ism", "ist", "ary", "ory",
)

# The words a vocabulary list never contains. Kept short on purpose: deciding
# that `monotonous` is too easy for Grade 8 is a judgement, and judgements are
# the model's job. This list only removes the words that would waste the
# model's attention getting there.
_STOP_WORD_TEXT = """
a about above after again against all almost alone along already also although
always am among an and another any anyone anything are around as ask asked at
away back be became because become been before began begin behind being below
beneath beside best better between beyond both but by call called came can
cannot could couldn did didn different do does doesn doing don done door down
during each early either else enough even ever every everyone everything except
eyes face fact far feel feet felt few find first five follow following for
found four from front full gave get give given go goes going gone good got
great green ground had half hand hands happen happened hard has have having he
head hear heard help her here herself high him himself his hold home how
however i if in inside into is it its itself just keep kept kind knew know known
land large last late later least leave left less let life light like little long
look looked looking made make man many may maybe me mean means men might mind
minute more morning most mother move much must my myself name near need never
new next night no none nor not nothing now number of off often old on once one
only open or other others our out over own part people perhaps place put quite
rather reach really right room round said same saw say saying says school sea
second see seem seemed seen set several shall she should show side since sit six
small so some someone something sometimes soon sound stand start started still
stood stop such sure take taken talk tell than that the their them themselves
then there these they thing things think this those though thought three through
time to today together told too took toward turn turned two under until up upon
us use used very voice wait walk want wanted was watch water way we well went
were what when where whether which while white who whole whose why will with
within without word words work world would year years yes yet you young your
yourself
"""

STOP_WORDS = frozenset(_STOP_WORD_TEXT.split())

# The model is asked to judge a list, not to read a book. Two hundred and fifty
# types is a long list of unusual words even for a twelve-chapter lesson.
DEFAULT_POOL_SIZE = 250


@dataclass(slots=True)
class WordType:
    """One distinct word in the book, with what the book says about it."""

    term: str
    surfaces: Counter = field(default_factory=Counter)
    total_in_book: int = 0
    total_in_range: int = 0
    unlicensed_capitals: int = 0
    first_chapter: int | None = None
    example: str = ""
    score: float = 0.0

    @property
    def dominant_surface(self) -> str:
        return self.surfaces.most_common(1)[0][0] if self.surfaces else self.term

    @property
    def never_lower_case(self) -> bool:
        """Whether the book capitalises this word every single time."""
        return bool(self.surfaces) and all(
            surface[0].isupper() for surface in self.surfaces
        )

    @property
    def looks_like_a_name(self) -> bool:
        """Whether this is a character, a place, or a brand rather than a word.

        The decisive evidence is simple and it took a wrong answer to find: a
        common noun appears in lower case *somewhere* in a novel, and a name
        never does. Position was the first thing tried and it is the weaker
        signal, because `Mr. Alder` and `Dr. Vance` are capitalised right after
        a full stop, which looks exactly like the start of a sentence.

        Position still does useful work as the tie-breaker. A word that is
        always capitalised but appears only once or twice, always at the start
        of a sentence, might genuinely be a common noun that never happened to
        appear mid-sentence, so it survives.
        """
        if not self.never_lower_case:
            return False
        return self.unlicensed_capitals >= 1 or self.total_in_book >= 3


def _licensed_capital(text: str, start: int, is_first_word: bool) -> bool:
    """Whether a capital letter here is explained by where it sits.

    The scan runs inside one sentence, which is why a full stop does not appear
    in the licensing set: a full stop *inside* a sentence is an abbreviation —
    `Mr.`, `Dr.`, `St.` — and the capital after it is a name, not a new
    sentence. Treating it as licensed is what let `Mr. Alder` through the
    proper-noun filter the first time.
    """
    if is_first_word:
        return True
    for index in range(start - 1, -1, -1):
        character = text[index]
        if character.isspace():
            continue
        return character in _LICENSING_CHARACTERS
    return True


def harvest(
    document: BookDocument,
    chapters: range | list[int],
    *,
    excluded: set[str] | None = None,
    minimum_length: int = 4,
    pool_size: int = DEFAULT_POOL_SIZE,
) -> list[WordType]:
    """Rank every word in a chapter range by how likely it is worth teaching.

    Counts are taken over the whole book but eligibility over the range, because
    "how unusual is this word" is a fact about the book and "did the student
    read it" is a fact about the lesson.
    """
    excluded = {normalize_term(term) for term in (excluded or set())}
    wanted = set(chapters)
    types: dict[str, WordType] = {}

    for chapter in document.chapters:
        in_range = chapter.number in wanted
        for sentence in chapter.sentences:
            text = chapter.slice(sentence.char_start, sentence.char_end)
            for position, match in enumerate(_WORD.finditer(text)):
                surface = match.group()
                key = normalize_term(surface)
                if not key:
                    continue

                entry = types.get(key)
                if entry is None:
                    entry = WordType(term=key)
                    types[key] = entry

                entry.surfaces[surface] += 1
                entry.total_in_book += 1

                if surface[0].isupper() and not _licensed_capital(
                    text, match.start(), position == 0
                ):
                    entry.unlicensed_capitals += 1

                if in_range:
                    entry.total_in_range += 1
                    if entry.first_chapter is None:
                        entry.first_chapter = chapter.number
                        entry.example = text

    pool = [
        entry
        for entry in types.values()
        if _eligible(entry, excluded=excluded, minimum_length=minimum_length)
    ]
    for entry in pool:
        entry.score = _score(entry)

    pool.sort(key=lambda entry: (-entry.score, entry.term))
    return pool[:pool_size]


def _eligible(entry: WordType, *, excluded: set[str], minimum_length: int) -> bool:
    if entry.total_in_range == 0:
        return False
    if len(entry.term) < minimum_length:
        return False
    if entry.term in STOP_WORDS or entry.term in excluded:
        return False
    if any(character.isdigit() for character in entry.term):
        return False
    if entry.looks_like_a_name:
        return False
    # An all-capitals word is an acronym, a sign, or a shout; none of the three
    # is a vocabulary entry.
    if all(surface.isupper() for surface in entry.surfaces):
        return False
    # A word that occurs once in a whole novel is as likely to be an extraction
    # artefact as a teachable word, and there is nowhere to look for a second
    # opinion about it.
    return entry.total_in_book >= 2


def _score(entry: WordType) -> float:
    """How promising a word looks before anyone has judged it.

    Rarity carries most of the weight: in a novel, the words a Grade 7 reader
    has to stop and think about are the ones the novel itself does not repeat.
    Length and Latinate suffixes are tie-breakers, not evidence.
    """
    rarity = 2.5 / (1.0 + math.log1p(entry.total_in_book))
    length = min(len(entry.term) - 4, 6) * 0.15
    academic = 0.4 if entry.term.endswith(_ACADEMIC_SUFFIXES) else 0.0
    # A word appearing several times in the lesson's own chapters is one the
    # student will meet again while reading it, which is worth a little.
    reinforced = 0.2 if entry.total_in_range >= 2 else 0.0
    return rarity + length + academic + reinforced


def render_pool(entries: list[WordType], *, example_characters: int = 180) -> str:
    """The word list a model is asked to judge.

    Each line is a word and one sentence showing the sense the book uses. That
    sentence is the only book text this stage sends anywhere, which is a large
    part of why the pool is harvested rather than requested.
    """
    lines: list[str] = []
    for entry in entries:
        example = entry.example.strip()
        if len(example) > example_characters:
            example = example[: example_characters - 1].rstrip() + "…"
        lines.append(
            f"- {entry.dominant_surface} "
            f"(appears {entry.total_in_range}x in these chapters): {example}"
        )
    return "\n".join(lines)
