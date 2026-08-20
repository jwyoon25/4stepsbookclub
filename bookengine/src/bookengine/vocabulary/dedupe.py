"""Making sure no word is taught twice, and deciding what "twice" means.

Two words being the same word is not one question, it is two. Whether `lurch`
and `Lurch,` are the same is a technical question with an obvious answer, and
this module answers it the same way everywhere by going through `normalize_term`
rather than inventing a second notion of equality. Whether `run`, `running` and
`ran` are one vocabulary entry or three is a teaching question with no obvious
answer, and this module refuses to decide it: `DedupeConfig.policy` does, and it
can be changed for a book without anything else moving.

What is not configurable is the exact case. Two rows in one workbook with the
same word on them is a defect however a tutor feels about word families, so
exact identity is enforced across the whole book regardless of policy, and
`scope` only widens or narrows how far the lemma policy reaches.

The other thing worth knowing about this module is `release`. Items get rejected
by the auditor and replaced, and a registry that never gave a word back would
shrink the available pool on every round until a lesson could not be filled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..config import DedupeConfig
from ..source.text import normalize_term

# Suffix stripping is only as good as its worst case, and its worst case is
# silently merging two unrelated words: `corner` reduced to `corn` would make
# them one entry and quietly drop a word from the book. So the rule-based
# fallback handles only the inflections it can get right nearly always —
# plurals, past tense, and present participles — and leaves comparatives and
# adverbs alone. Those are merged only when lemminflect is installed, which is
# what the extra is for.
_MIN_PLURAL_LENGTH = 4
_MIN_PAST_LENGTH = 5
_MIN_PARTICIPLE_LENGTH = 6
_MIN_STEM_LENGTH = 3

# Endings where a trailing `s` is part of the word rather than a plural.
_NOT_PLURAL_ENDINGS = ("ss", "us", "is", "as", "os")

_DOUBLE_CONSONANTS = "bdfglmnprtz"


@runtime_checkable
class Lemmatizer(Protocol):
    """Something that can say which dictionary words a surface form belongs to."""

    name: str

    def lemmas(self, term: str) -> frozenset[str]: ...


class RuleLemmatizer:
    """The always-available fallback: conservative English suffix rules.

    Every result set includes the surface form itself. That is what makes the
    intersection test safe: two words are only merged when they agree on some
    form, so a wrong guess about one word cannot pull in a word that never
    produced that guess.
    """

    name = "rules"

    def lemmas(self, term: str) -> frozenset[str]:
        word = normalize_term(term)
        if not word:
            return frozenset()

        found = {word}
        for candidate in (
            *self._plural(word),
            *self._past(word),
            *self._participle(word),
        ):
            if len(candidate) >= _MIN_STEM_LENGTH:
                found.add(candidate)
        return frozenset(found)

    @staticmethod
    def _plural(word: str) -> tuple[str, ...]:
        if len(word) < _MIN_PLURAL_LENGTH or not word.endswith("s"):
            return ()
        if word.endswith(_NOT_PLURAL_ENDINGS):
            return ()
        if word.endswith("ies"):
            return (word[:-3] + "y",)
        if word.endswith("ves"):
            return (word[:-3] + "f", word[:-3] + "fe")
        if word.endswith(("ches", "shes", "sses", "xes", "zes")):
            return (word[:-2],)
        return (word[:-1],)

    @staticmethod
    def _past(word: str) -> tuple[str, ...]:
        if len(word) < _MIN_PAST_LENGTH or not word.endswith("ed"):
            return ()
        if word.endswith("ied"):
            return (word[:-3] + "y",)
        stem = word[:-2]
        results = [stem, word[:-1]]
        # `stopped` -> `stop`: a doubled final consonant before the ending is
        # spelling, not part of the word.
        if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] in _DOUBLE_CONSONANTS:
            results.append(stem[:-1])
        return tuple(results)

    @staticmethod
    def _participle(word: str) -> tuple[str, ...]:
        if len(word) < _MIN_PARTICIPLE_LENGTH or not word.endswith("ing"):
            return ()
        stem = word[:-3]
        # `making` -> `make`, `running` -> `run`.
        results = [stem, stem + "e"]
        if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] in _DOUBLE_CONSONANTS:
            results.append(stem[:-1])
        return tuple(results)


class LemminflectLemmatizer:
    """The accurate option, when the optional extra is installed.

    Worth the extra because it knows the irregular forms rules cannot reach —
    `saw`/`see`, `ran`/`run`, `better`/`good` — which are exactly the words a
    workbook would otherwise teach twice under two spellings.
    """

    name = "lemminflect"

    def __init__(self) -> None:
        from lemminflect import getAllLemmas, getAllLemmasOOV

        self._all = getAllLemmas
        self._oov = getAllLemmasOOV

    def lemmas(self, term: str) -> frozenset[str]:
        word = normalize_term(term)
        if not word:
            return frozenset()

        found = {word}
        for source in (self._all(word), self._oov(word, upos="NOUN")):
            for forms in source.values():
                found.update(form.lower() for form in forms)
        return frozenset(found)


def build_lemmatizer() -> Lemmatizer:
    """Prefer the accurate lemmatizer, and be honest when it is not installed.

    The caller records `name` in the run's audit artifact, so a workbook built
    without the extra says so rather than implying a word-family check it did
    not really perform.
    """
    try:
        return LemminflectLemmatizer()
    except Exception:  # noqa: BLE001 - an optional extra, absent or broken
        return RuleLemmatizer()


@dataclass(slots=True)
class DuplicateRegistry:
    """Who has claimed which word, and what a second claim would collide with."""

    config: DedupeConfig
    lemmatizer: Lemmatizer = field(default_factory=build_lemmatizer)

    # Exact identity is tracked across the whole book whatever the policy says.
    _exact: dict[str, tuple[str, int]] = field(default_factory=dict, init=False)
    # Lemma claims are keyed by scope, so "book" shares one bucket and "lesson"
    # gives each lesson its own.
    _lemmas: dict[tuple[int, str], tuple[str, int]] = field(
        default_factory=dict, init=False
    )
    blocked: list[str] = field(default_factory=list, init=False)

    def key(self, term: str) -> str:
        """The identity a term is claimed under."""
        return normalize_term(term)

    def _bucket(self, lesson: int) -> int:
        return 0 if self.config.scope == "book" else lesson

    def _lemmas_for(self, term: str) -> frozenset[str]:
        if self.config.policy != "lemma":
            return frozenset()
        return self.lemmatizer.lemmas(term)

    def conflict(self, term: str, *, lesson: int) -> str | None:
        """The already-claimed word this one would duplicate, if any."""
        identity = self.key(term)
        if not identity:
            return f"{term!r} is not a usable vocabulary word."

        claimed = self._exact.get(identity)
        if claimed is not None:
            return self._describe(term, claimed, "the same word")

        bucket = self._bucket(lesson)
        for lemma in self._lemmas_for(term):
            holder = self._lemmas.get((bucket, lemma))
            if holder is not None and holder[0] != identity:
                return self._describe(term, holder, f"the same word family ({lemma})")

        return None

    def claim(self, term: str, *, lesson: int) -> None:
        """Record that this lesson is teaching this word."""
        identity = self.key(term)
        self._exact[identity] = (identity, lesson)
        bucket = self._bucket(lesson)
        for lemma in self._lemmas_for(term):
            self._lemmas.setdefault((bucket, lemma), (identity, lesson))

    def release(self, term: str, *, lesson: int) -> None:
        """Give a word back, so a rejected item does not shrink the pool.

        Only claims this term actually holds are removed. A lemma claimed by a
        different word that happens to share a family stays where it is.
        """
        identity = self.key(term)
        if self._exact.get(identity, (None, None))[0] == identity:
            self._exact.pop(identity, None)

        bucket = self._bucket(lesson)
        for lemma in self._lemmas_for(term):
            if self._lemmas.get((bucket, lemma), (None, None))[0] == identity:
                self._lemmas.pop((bucket, lemma), None)

    def record_block(self, message: str) -> None:
        """Keep a rejection for the audit artifact."""
        self.blocked.append(message)

    def claimed_terms(self) -> list[str]:
        return sorted(self._exact)

    @property
    def policy_note(self) -> str:
        """How this run decided what counted as a duplicate."""
        if self.config.policy == "exact":
            return (
                "Exact duplicates were blocked across the whole book. Word "
                "families were not merged, so `run` and `running` could both "
                "be taught."
            )
        reach = "the whole book" if self.config.scope == "book" else "each lesson"
        return (
            f"Exact duplicates were blocked across the whole book, and word "
            f"families were merged within {reach} using the "
            f"{self.lemmatizer.name} lemmatizer."
        )

    def _describe(
        self, term: str, holder: tuple[str, int], reason: str
    ) -> str:
        held, lesson = holder
        return (
            f"{term!r} duplicates {held!r}, already taught in lesson {lesson} "
            f"({reason})."
        )


def conflicts_among(
    terms: list[tuple[str, int]],
    config: DedupeConfig,
    lemmatizer: Lemmatizer | None = None,
) -> list[str]:
    """Replay a finished set of (term, lesson) pairs and report what collides.

    The registry the pipeline used is not consulted: this builds a fresh one
    and walks the set that is actually about to be exported. Rows change after
    selection — an audit rejects one, a replacement takes its place, another
    fails final verification — so the set the registry believed in is not
    necessarily the set leaving the engine, and the guarantee is about the
    second one.

    Using the registry rather than a second comparison is the point. A final
    check with its own idea of what "the same word" means would prove something
    the job never asked for, and would pass a run that taught `run` and
    `running` under a policy that merges them.
    """
    registry = DuplicateRegistry(config, lemmatizer=lemmatizer or build_lemmatizer())
    found: list[str] = []

    for term, lesson in terms:
        clash = registry.conflict(term, lesson=lesson)
        if clash is not None:
            found.append(clash)
            continue
        registry.claim(term, lesson=lesson)

    return found
