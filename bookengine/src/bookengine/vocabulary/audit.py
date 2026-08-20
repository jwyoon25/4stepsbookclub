"""The second look, taken by something that did not do the first.

The brief is blunt about what this must not be: appending "double-check your
work" to the prompt that produced the work. That fails because a model asked to
review its own reasoning in the same context will defend it. So the audit runs
in a fresh conversation, on a different provider where the configuration allows
one, and is told it is inspecting somebody else's list.

It is also given a deliberately narrow job. It does not check whether the
quotation is really in the book, because that has already been proved and its
opinion could only be wrong. It checks the things no code can: whether the
definition matches the sense used in the passage, whether the Korean is natural,
whether the context sentence describes what is actually happening, whether the
word suits the audience, and whether two entries are teaching the same idea
under different spellings.

A FAIL sends the item back to be replaced. That is the point of a large
candidate pool.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import JobConfig
from ..errors import StructuredResponseError
from ..llm.base import Message
from ..llm.chain import ProviderChain
from ..llm.structured import generate_structured
from ..prompts import PromptLibrary
from ..source.document import BookDocument
from ..source.search import context_for_locator
from ..source.text import normalize_term
from .models import AUDIT_ASSESSMENT_LABELS, AuditVerdict, VocabularyItem
from .schemas import AuditReport

# Items per audit request. Small enough that a free endpoint answers in full,
# large enough that the auditor can notice two entries teaching one idea.
AUDIT_BATCH = 8

# One paragraph either side, the same window the entry was written from.
CONTEXT_PARAGRAPHS = 1

# How much source context one entry may carry. Eight entries at this size is a
# request a free endpoint still answers; the target paragraph is never trimmed,
# so what a tighter budget costs is the neighbours' outer ends.
CONTEXT_CHARACTER_BUDGET = 1800

# What the auditor is told when the source could not be produced for an entry.
# It reads as a refusal rather than as an absence, because an auditor that
# thinks it has the source and does not is the exact failure being avoided.
NO_CONTEXT = (
    "unavailable — this entry cannot be judged on context accuracy, so mark "
    "context_accuracy INACCURATE"
)


def _render_item(
    index: int, item: VocabularyItem, document: BookDocument
) -> str:
    """One entry as the auditor sees it, with the book underneath it.

    Without the surrounding source, `context_accuracy` is not a question the
    auditor can answer. "Thomas realises Minho has betrayed him" is either
    true of these paragraphs or it is not, and a model with only a
    two-sentence excerpt to go on has nothing to check it against — so it
    checks it against its memory of the novel, which is the one source this
    engine does not accept. Supplying the paragraphs is what turns that field
    from a guess into a reading.

    The source is cut from the `BookDocument` at the item's own locator, so it
    is the same text the entry was written from and no model had a hand in
    choosing it.
    """
    return "\n".join(
        [
            f"### Entry {index}",
            f"Word: {item.term}",
            f"English definition: {item.definition}",
            f"Korean meaning: {item.korean_meaning}",
            f"Excerpt from the book: {item.excerpt}",
            f"Excerpt context: {item.excerpt_context}",
            f"Chapter: {item.chapter_reference}",
            "",
            f"SOURCE CONTEXT for entry {index} (from the book itself):",
            _render_source(item, document),
        ]
    )


def _render_source(item: VocabularyItem, document: BookDocument) -> str:
    """The paragraphs around this item's excerpt, or an honest refusal."""
    if item.locator is None:
        return NO_CONTEXT
    try:
        window = context_for_locator(
            document,
            item.locator,
            paragraphs_before=CONTEXT_PARAGRAPHS,
            paragraphs_after=CONTEXT_PARAGRAPHS,
        )
    except (KeyError, StopIteration):
        return NO_CONTEXT
    return window.as_prompt_block(limit=CONTEXT_CHARACTER_BUDGET)


def audit_batch(
    items: list[VocabularyItem],
    job: JobConfig,
    document: BookDocument,
    chain: ProviderChain,
    prompts: PromptLibrary,
) -> dict[str, AuditVerdict]:
    """Judge a batch of finished items, returning a verdict per word.

    An unusable reply is not a pass. Items the auditor did not return a verdict
    for are simply absent from the result, and the caller treats absence as
    "not audited", which cannot become READY.
    """
    if not items:
        return {}

    rendered = prompts.render(
        "audit",
        audience=job.audience.label,
        book_title=job.book.title or document.title,
        item_count=len(items),
        items="\n\n".join(
            _render_item(index, item, document)
            for index, item in enumerate(items, start=1)
        ),
    )

    try:
        report, completion = _ask(chain, rendered)
    except StructuredResponseError:
        return {}

    verdicts: dict[str, AuditVerdict] = {}
    for entry in report.items:
        verdicts[normalize_term(entry.word)] = AuditVerdict(
            verdict=str(entry.verdict),
            difficulty=str(entry.difficulty),
            definition_accuracy=str(entry.definition_accuracy),
            korean_accuracy=str(entry.korean_accuracy),
            context_accuracy=str(entry.context_accuracy),
            excerpt_fit=str(entry.excerpt_fit),
            notes=entry.notes,
            provider=completion.provider,
            model=completion.model,
        )
    return verdicts


def _ask(chain: ProviderChain, rendered):
    return generate_structured(
        chain,
        [
            Message(role="system", content=rendered.system),
            Message(role="user", content=rendered.user),
        ],
        AuditReport,
    )


def apply_verdicts(
    items: list[VocabularyItem], verdicts: dict[str, AuditVerdict]
) -> tuple[list[VocabularyItem], list[VocabularyItem]]:
    """Record each verdict and split the batch into survivors and casualties.

    An item with no verdict is a casualty. Treating a missing verdict as a pass
    would make a truncated reply from a rate-limited endpoint look exactly like
    an approved list, which is the failure this whole stage exists to prevent.
    """
    passed: list[VocabularyItem] = []
    failed: list[VocabularyItem] = []

    for item in items:
        verdict = verdicts.get(normalize_term(item.term))
        item.audit = verdict
        if verdict is None:
            item.fail("The auditor returned no verdict for this word.")
            failed.append(item)
            continue

        item.provenance.auditor_provider = verdict.provider
        item.provenance.auditor_model = verdict.model
        if verdict.passed:
            passed.append(item)
        else:
            item.fail(_explain(verdict))
            failed.append(item)

    return passed, failed


def _explain(verdict: AuditVerdict) -> str:
    """Why the auditor rejected an item, in a sentence an operator can read.

    The complaints come from `AuditVerdict.complaints`, which is the same list
    the pass/fail decision is made from. Two lists would let an item be
    rejected for a reason the message does not mention.
    """
    problems = [
        f"{AUDIT_ASSESSMENT_LABELS[name]} ({getattr(verdict, name)})"
        for name in verdict.complaints
    ]

    listed = ", ".join(problems) if problems else "the entry as a whole"
    note = f" Auditor: {verdict.notes}" if verdict.notes else ""
    return f"The independent audit rejected {listed}.{note}"


# How far apart the writer and the auditor actually were, strongest first. The
# order matters: a run's independence is the weakest any of its items reached.
INDEPENDENCE_ORDER = ("none", "model", "provider")

# What was not recorded cannot be claimed. An item missing either side's
# provenance is treated as the weakest reading rather than the likeliest one.
UNKNOWN_INDEPENDENCE = "none"


@dataclass(frozen=True, slots=True)
class Independence:
    """How independent one item's audit actually was, and from what."""

    level: str
    generator: str
    auditor: str

    def satisfies(self, requirement: str) -> bool:
        """Whether this clears the job's bar.

        `provider` is met only by two providers; `model` by two providers or
        two models on one; `none` by anything, including a model marking its
        own work.
        """
        return INDEPENDENCE_ORDER.index(self.level) >= INDEPENDENCE_ORDER.index(
            requirement
        )

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "generator": self.generator,
            "auditor": self.auditor,
        }


def independence_of(item: VocabularyItem) -> Independence:
    """What actually wrote this item and what actually audited it.

    From the completions, not from the job file. Both chains fall back to the
    same list, so a job naming Groq for writing and NVIDIA for auditing can
    have Gemini answer both on a bad afternoon — and the configuration would
    still read as two providers. This asks the only question with an answer:
    which endpoint's words are in this row, and which endpoint approved them.
    """
    provenance = item.provenance
    generator = _label(provenance.generator_provider, provenance.generator_model)
    auditor = _label(provenance.auditor_provider, provenance.auditor_model)

    if not provenance.generator_provider or not provenance.auditor_provider:
        return Independence(UNKNOWN_INDEPENDENCE, generator, auditor)
    if provenance.generator_provider != provenance.auditor_provider:
        return Independence("provider", generator, auditor)
    if provenance.generator_model != provenance.auditor_model:
        return Independence("model", generator, auditor)
    return Independence("none", generator, auditor)


def weakest_independence(items: list[VocabularyItem]) -> str:
    """The independence a whole run may claim: the least any item reached.

    A run is not independently audited on average. One row marked by its own
    writer is one row nobody checked, so the run's word for itself is the word
    that row earned.
    """
    if not items:
        return UNKNOWN_INDEPENDENCE
    return min(
        (independence_of(item).level for item in items),
        key=INDEPENDENCE_ORDER.index,
    )


def _label(provider: str | None, model: str | None) -> str:
    return f"{provider}/{model}" if provider else "unrecorded"
