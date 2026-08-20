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

from ..config import JobConfig
from ..errors import StructuredResponseError
from ..llm.base import Message
from ..llm.chain import ProviderChain
from ..llm.structured import generate_structured
from ..prompts import PromptLibrary
from ..source.document import BookDocument
from ..source.text import normalize_term
from .models import AuditVerdict, VocabularyItem
from .schemas import AuditReport

# Items per audit request. Small enough that a free endpoint answers in full,
# large enough that the auditor can notice two entries teaching one idea.
AUDIT_BATCH = 8


def _render_item(index: int, item: VocabularyItem) -> str:
    return "\n".join(
        [
            f"### Entry {index}",
            f"Word: {item.term}",
            f"English definition: {item.definition}",
            f"Korean meaning: {item.korean_meaning}",
            f"Excerpt from the book: {item.excerpt}",
            f"Excerpt context: {item.excerpt_context}",
            f"Chapter: {item.chapter_reference}",
        ]
    )


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
            _render_item(index, item) for index, item in enumerate(items, start=1)
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


# The values each assessment field may take, from `schemas.py`. Anything not
# listed here is a complaint. They are spelled out rather than derived because
# an assessment silently reading as acceptable is exactly the direction this
# stage must not fail in.
_ACCEPTABLE = {
    "definition_accuracy": {"ACCURATE"},
    "korean_accuracy": {"ACCURATE"},
    "context_accuracy": {"ACCURATE"},
    "excerpt_fit": {"GOOD"},
    "difficulty": {"APPROPRIATE"},
}

_FIELD_LABELS = {
    "definition_accuracy": "the definition",
    "korean_accuracy": "the Korean meaning",
    "context_accuracy": "the context sentence",
    "excerpt_fit": "the excerpt",
    "difficulty": "the difficulty",
}


def _explain(verdict: AuditVerdict) -> str:
    """Why the auditor rejected an item, in a sentence an operator can read."""
    problems = []
    for field_name, acceptable in _ACCEPTABLE.items():
        value = getattr(verdict, field_name, "")
        if value.upper() not in acceptable:
            problems.append(f"{_FIELD_LABELS[field_name]} ({value})")

    listed = ", ".join(problems) if problems else "the entry as a whole"
    note = f" Auditor: {verdict.notes}" if verdict.notes else ""
    return f"The independent audit rejected {listed}.{note}"
