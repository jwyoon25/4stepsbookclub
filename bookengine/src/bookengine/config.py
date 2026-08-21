"""The job description: which book, which lessons, for whom, and how strictly.

A job is a small YAML file that a person writes, so the errors it produces are
written for a person. "Lesson 3 covers chapters 25-36, but the book has 24
chapters" is a sentence someone can act on; a schema path is not.

Two rules here are worth stating out loud. Model identifiers live in this file
or in the environment and never in the pipeline, so a free model disappearing
is a configuration change. And the chapter ranges are checked twice — once for
internal sense before the book is opened, and again against the book's actual
chapter map — because the first check is cheap and the second is the one that
matters.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import ConfigError

_ENVIRONMENT = re.compile(r"\$\{(?P<name>[A-Z0-9_]+)(?::-(?P<default>[^}]*))?\}")


class _Strict(BaseModel):
    """Reject unknown keys, so a misspelled setting is not silently ignored."""

    model_config = ConfigDict(extra="forbid")


class BookConfig(_Strict):
    """Which book, and what the operator already knows about it."""

    path: Path
    title: str | None = None
    # The operator's own chapter count, read off the book's contents page. It
    # is the only fact about a book that the PDF cannot supply about itself,
    # which makes it the most valuable check ingestion has.
    expected_chapters: int | None = Field(default=None, ge=1, le=500)


class AudienceConfig(_Strict):
    """Who the vocabulary is for."""

    grade_min: int = Field(ge=1, le=13)
    grade_max: int = Field(ge=1, le=13)
    description: str | None = None

    @model_validator(mode="after")
    def _ordered(self) -> AudienceConfig:
        if self.grade_min > self.grade_max:
            raise ValueError(
                f"grade_min ({self.grade_min}) is above grade_max ({self.grade_max})."
            )
        return self

    @property
    def label(self) -> str:
        if self.grade_min == self.grade_max:
            return f"Grade {self.grade_min}"
        return f"Grades {self.grade_min}-{self.grade_max}"


class LessonConfig(_Strict):
    """One lesson and the chapters it covers."""

    lesson: int = Field(ge=1)
    start_chapter: int = Field(ge=1)
    end_chapter: int = Field(ge=1)
    title: str | None = None

    @model_validator(mode="after")
    def _ordered(self) -> LessonConfig:
        if self.start_chapter > self.end_chapter:
            raise ValueError(
                f"Lesson {self.lesson} starts at chapter {self.start_chapter} "
                f"and ends at chapter {self.end_chapter}."
            )
        return self

    @property
    def chapters(self) -> range:
        return range(self.start_chapter, self.end_chapter + 1)

    @property
    def reading_range(self) -> str:
        if self.start_chapter == self.end_chapter:
            return f"Chapter {self.start_chapter}"
        return f"Chapters {self.start_chapter}-{self.end_chapter}"


class CandidateConfig(_Strict):
    """Where the pool of possible vocabulary words comes from.

    `harvest` is the default and the safer of the two. It takes every word type
    out of the lesson's own chapters, throws out the ones no vocabulary list
    contains, and asks a model to judge what is left. Every candidate therefore
    provably occurs in the reading, and the only book text that leaves this
    machine is one example sentence per word rather than several chapters of a
    copyrighted novel.

    `model` is the arrangement the brief describes: hand the model the chapters
    and ask it for words. It is kept because it finds phrasal and idiomatic
    items a word-type harvest cannot see, and because a book with unusual
    vocabulary may defeat the harvester's ranking. Its output is filtered
    through the same occurrence check, so it is no less verified — only more
    expensive and less private.
    """

    mode: Literal["harvest", "model", "hybrid"] = "harvest"
    # How many word types the harvester shortlists before any model sees them.
    pool_size: int = Field(default=250, ge=10, le=2000)
    # Candidates scored per request. Free endpoints truncate long replies, and a
    # truncated ranking silently loses the words at the end of the list.
    rank_batch: int = Field(default=50, ge=5, le=200)
    # Characters of book text per request in `model` mode.
    chunk_characters: int = Field(default=9000, ge=1000, le=60000)
    # A candidate the model marks this risky is dropped before it costs a quote.
    max_exclusion_risk: int = Field(default=3, ge=1, le=5)


class DedupeConfig(_Strict):
    """How much of a word's family counts as the same word.

    Whether `run`, `running`, and `ran` are one vocabulary entry or three is a
    teaching decision, not a technical one, so it is a setting. Exact duplicates
    are blocked whatever this says; the policy only widens the net.
    """

    policy: Literal["exact", "lemma"] = "lemma"
    scope: Literal["book", "lesson"] = "book"


class ExcerptConfig(_Strict):
    """What makes a passage usable as a workbook quotation."""

    # 600 is the vocabulary excerpt limit in the workbook's own content schema.
    # Generating past it would produce rows the workbook builder rejects.
    max_characters: int = Field(default=600, ge=40, le=600)
    min_characters: int = Field(default=40, ge=1)
    max_sentences: int = Field(default=2, ge=1, le=4)
    prefer_unrepaired: bool = True
    # What to do with a passage that reads a word the book could not confirm
    # the spelling of.
    #
    # Ingestion rejoins words broken across a line, and for most of them the
    # book settles the question itself: `extraordinary` appears whole
    # elsewhere, `self-conscious` appears hyphenated elsewhere. Where it
    # settles neither, the engine has produced a reading it cannot prove.
    #
    # Neither value exports one. `skip` does not select the passage at all, so
    # another occurrence or another word is used — which is right nearly
    # always, because the pool is large and both are cheap. `review` selects it
    # and parks the item at NEEDS_REVIEW, where a person can read the passage
    # and decide; it is for working out why a heavily hyphenated book is coming
    # up short, and it costs a place in the lesson either way.
    #
    # There is deliberately no third value. "This quotation is the book's own
    # words" is the claim the whole engine exists to make, and a setting that
    # could turn an unproved reading into a Ready row would make that claim
    # conditional on a config file.
    unconfirmed_repairs: Literal["skip", "review"] = "skip"

    @model_validator(mode="after")
    def _ordered(self) -> ExcerptConfig:
        if self.min_characters > self.max_characters:
            raise ValueError(
                f"min_characters ({self.min_characters}) is above max_characters "
                f"({self.max_characters})."
            )
        return self


class LimitsConfig(_Strict):
    """The ceiling on what one lesson may spend before the run gives up.

    The candidate pool is the real bound on a lesson's work: each candidate is
    taken from it once and never returned, so a lesson cannot attempt more
    words than it was given. This is the second bound, against the case the
    first one does not cover — an endpoint that answers every request with
    something unusable, where the pool drains at full price and produces
    nothing.

    Expressed per candidate rather than as a flat number so that it scales with
    the pool an operator configured, and set high enough that ordinary retries
    and a fallback or two do not trip it. Reaching it is reported as what it
    is: a run stopped by its budget, not a book that ran out of words.
    """

    provider_calls_per_candidate: int = Field(default=8, ge=1, le=100)


class ExclusionConfig(_Strict):
    """Words this book should not teach.

    The engine's own exclusions — proper nouns, invented terminology, words far
    below the audience — are audience rules and live in the prompts and the
    filters. This is the per-book escape hatch, so that a book with its own
    invented slang can name it without that knowledge being compiled into a
    generic engine.
    """

    terms: list[str] = Field(default_factory=list)
    allow_invented_terms: bool = False


class ProviderConfig(_Strict):
    """One inference endpoint, named entirely in configuration."""

    provider: str
    model: str
    base_url: str | None = None
    api_key_env: str | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=4096, ge=256, le=32768)
    timeout_seconds: float = Field(default=90.0, gt=0)

    @property
    def label(self) -> str:
        return f"{self.provider}/{self.model}"


class AuditConfig(_Strict):
    """What "independent" has to mean, and what happens when it does not hold.

    The audit stage is worth having because something other than the writer
    looked at the work. Both chains fall back to the same list, though, so a
    run configured with two providers can end up with one answering both — and
    a run that then reported an independent audit would be claiming a check it
    did not perform.

    `requirement` says what counts. `provider` is the strict reading and the
    default: two endpoints, which fail differently and were trained by
    different people. `model` accepts two models on one provider, which is
    weaker — models from one lab share training data and failure modes — but is
    a real second opinion and is sometimes all a free tier offers. `none` is
    for a run where the audit is kept for its rubric rather than for its
    independence, and it still records what actually happened.

    `on_shared` says what to do about items that fall short. Retrying is not
    among the options: if the auditor was the generator, it will be the
    generator next time too. `needs_review` keeps the work and refuses to call
    it proved, which is the honest default. `fail` is for a run whose output
    goes straight to students. `allow` exports it and says so in the artifact.
    """

    requirement: Literal["provider", "model", "none"] = "provider"
    on_shared: Literal["needs_review", "fail", "allow"] = "needs_review"


class LLMConfig(_Strict):
    """Which endpoints do the generating and which do the auditing."""

    generator: ProviderConfig
    auditor: ProviderConfig
    fallbacks: list[ProviderConfig] = Field(default_factory=list)
    cache: bool = True
    max_attempts: int = Field(default=3, ge=1, le=6)
    audit: AuditConfig = Field(default_factory=AuditConfig)

    @property
    def configured_independence(self) -> str:
        """What the configuration alone promises, before anything is called.

        Worth reporting and not worth trusting. A job naming two providers can
        still have one answer both calls, because both chains fall back to the
        same list; a run's real independence is computed from the completions
        that came back, and this is only the intent.
        """
        if self.generator.provider != self.auditor.provider:
            return "provider"
        if self.generator.model != self.auditor.model:
            return "model"
        return "none"

    @property
    def audit_is_independent(self) -> bool:
        """Whether the configuration asks for two different models at all."""
        return self.configured_independence != "none"


class OutputConfig(_Strict):
    """Where a run's artifacts are written."""

    directory: Path = Path("output")
    tsv_name: str = "vocabulary.tsv"
    json_name: str = "vocabulary.json"
    audit_name: str = "audit.json"
    # Off by default: the paste target is the first data row of a tab that
    # already carries its headings, so a header line would become item 1.
    include_header: bool = False


class JobConfig(_Strict):
    """A complete vocabulary job."""

    book: BookConfig
    audience: AudienceConfig
    lessons: list[LessonConfig] = Field(min_length=1)
    vocabulary_per_lesson: int = Field(default=20, ge=1, le=100)
    candidates_per_lesson: int = Field(default=50, ge=1, le=400)
    candidates: CandidateConfig = Field(default_factory=CandidateConfig)
    dedupe: DedupeConfig = Field(default_factory=DedupeConfig)
    excerpt: ExcerptConfig = Field(default_factory=ExcerptConfig)
    exclusions: ExclusionConfig = Field(default_factory=ExclusionConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    llm: LLMConfig
    output: OutputConfig = Field(default_factory=OutputConfig)

    # Set by `load_job`; not part of the file.
    source_path: Path | None = None

    @field_validator("lessons")
    @classmethod
    def _distinct_and_disjoint(cls, lessons: list[LessonConfig]) -> list[LessonConfig]:
        numbers = [lesson.lesson for lesson in lessons]
        duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
        if duplicates:
            raise ValueError(
                "Lesson numbers must be unique; these appear more than once: "
                + ", ".join(str(number) for number in duplicates)
            )

        ordered = sorted(lessons, key=lambda lesson: lesson.start_chapter)
        for earlier, later in zip(ordered, ordered[1:], strict=False):
            if later.start_chapter <= earlier.end_chapter:
                raise ValueError(
                    f"Lesson {earlier.lesson} ({earlier.reading_range}) and lesson "
                    f"{later.lesson} ({later.reading_range}) overlap. A word taught "
                    "in one lesson would be taught again in the other."
                )
        return lessons

    @model_validator(mode="after")
    def _pool_is_big_enough(self) -> JobConfig:
        if self.candidates_per_lesson < self.vocabulary_per_lesson:
            raise ValueError(
                f"candidates_per_lesson ({self.candidates_per_lesson}) is below "
                f"vocabulary_per_lesson ({self.vocabulary_per_lesson}). There "
                "would be nothing to replace a rejected candidate with."
            )
        return self

    @property
    def pool_is_comfortable(self) -> bool:
        """Whether there is room to reject candidates without starting over."""
        return self.candidates_per_lesson >= self.vocabulary_per_lesson * 2

    @property
    def total_requested(self) -> int:
        return len(self.lessons) * self.vocabulary_per_lesson

    @property
    def chapter_span(self) -> tuple[int, int]:
        return (
            min(lesson.start_chapter for lesson in self.lessons),
            max(lesson.end_chapter for lesson in self.lessons),
        )

    def lesson(self, number: int) -> LessonConfig:
        for lesson in self.lessons:
            if lesson.lesson == number:
                return lesson
        raise KeyError(number)


def _expand(value: object) -> object:
    """Replace `${NAME}` with the environment, recursively.

    Model identifiers and API keys belong in the environment; a job file that
    names them directly would put a free provider's current model catalogue
    into version control, which is the one thing about free providers that is
    certain to go stale.
    """
    if isinstance(value, dict):
        return {key: _expand(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand(item) for item in value]
    if not isinstance(value, str):
        return value

    def substitute(match: re.Match[str]) -> str:
        name = match.group("name")
        default = match.group("default")
        found = os.environ.get(name)
        if found is not None:
            return found
        if default is not None:
            return default
        raise ConfigError(
            f"The job refers to ${{{name}}} but that environment variable is "
            f"not set. Set it, or write `${{{name}:-a-default}}` in the job file."
        )

    return _ENVIRONMENT.sub(substitute, value)


def load_job(path: Path | str) -> JobConfig:
    """Read a job file, expand the environment, and validate what it says.

    Relative paths inside the file resolve against the file's own directory, so
    a job can be moved without being rewritten.
    """
    path = Path(path).resolve()
    if not path.is_file():
        raise ConfigError(f"No such job configuration: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as cause:
        raise ConfigError(f"{path.name} is not valid YAML: {cause}") from cause

    if not isinstance(raw, dict):
        raise ConfigError(f"{path.name} should contain a mapping of settings.")

    try:
        job = JobConfig.model_validate(_expand(raw))
    except ConfigError:
        raise
    except Exception as cause:
        raise ConfigError(f"{path.name} is not a usable job:\n{cause}") from cause

    job.source_path = path
    base = path.parent
    if not job.book.path.is_absolute():
        job.book.path = (base / job.book.path).resolve()
    if not job.output.directory.is_absolute():
        job.output.directory = (base / job.output.directory).resolve()
    if job.book.title is None:
        job.book.title = job.book.path.stem.replace("-", " ").replace("_", " ").strip()

    return job


def validate_lessons_against_book(
    job: JobConfig, chapter_numbers: list[int]
) -> list[str]:
    """Check the lesson plan against the chapters the book actually has.

    Missing chapters are fatal and raise. Chapters the plan never reaches are
    returned as notes, because leaving out a book's last two chapters is a
    normal editorial choice and not the engine's business to override.
    """
    available = set(chapter_numbers)
    problems: list[str] = []

    for lesson in job.lessons:
        missing = sorted(set(lesson.chapters) - available)
        if missing:
            listed = ", ".join(str(number) for number in missing[:8])
            more = "" if len(missing) <= 8 else f", and {len(missing) - 8} more"
            problems.append(
                f"Lesson {lesson.lesson} covers {lesson.reading_range}, but the "
                f"book has no chapter {listed}{more}."
            )

    if problems:
        detected = (
            f"{min(available)}-{max(available)}" if available else "none detected"
        )
        raise ConfigError(
            "The lesson plan does not fit this book.\n"
            + "\n".join(f"  - {problem}" for problem in problems)
            + f"\nChapters found in the book: {len(available)} ({detected})."
        )

    covered = {number for lesson in job.lessons for number in lesson.chapters}
    uncovered = sorted(available - covered)
    notes: list[str] = []
    if uncovered:
        listed = ", ".join(str(number) for number in uncovered[:10])
        more = "" if len(uncovered) <= 10 else f", and {len(uncovered) - 10} more"
        notes.append(
            f"{len(uncovered)} chapter(s) are in the book but in no lesson: "
            f"{listed}{more}."
        )
    if not job.pool_is_comfortable:
        notes.append(
            f"candidates_per_lesson is {job.candidates_per_lesson} for "
            f"{job.vocabulary_per_lesson} words. Two to three times the final "
            "count leaves room to reject a candidate without regenerating."
        )
    return notes
