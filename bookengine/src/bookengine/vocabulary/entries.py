"""Writing the definition, the Korean meaning, and the line of story context.

This is the stage where a model writes text that a student will read, so it is
the stage where grounding matters most and is hardest to enforce. The quotation
cannot be wrong — it was cut from the book — but a definition can be, and a
sentence of context can be a half-remembered plot summary dressed up as an
observation.

The defence is what the model is shown. It gets the excerpt, the paragraph the
excerpt sits in, and the paragraphs on either side, and it is asked about the
sense used *here*. It is never asked what happens in the book. A model that has
never read this novel and a model that has read it twice should produce the same
answer from this prompt, and if they do not, the one that used its memory is the
one that is wrong.

What comes back is still only checked for shape and length. Whether a Korean
gloss is natural is not a thing code can decide, which is exactly why the audit
stage exists and why it runs on a different provider.
"""

from __future__ import annotations

from ..config import JobConfig
from ..llm.base import Completion, Message
from ..llm.chain import ProviderChain
from ..llm.structured import generate_structured
from ..prompts import PromptLibrary
from ..source.document import BookDocument
from ..source.search import CONTEXT_CHARACTER_LIMIT, context_for_locator
from .models import VocabularyItem
from .schemas import EntryDraft

# One paragraph either side. Enough for a model to see what is happening;
# little enough that the request stays small and the book stays local.
CONTEXT_PARAGRAPHS = 1


def draft_entry(
    document: BookDocument,
    job: JobConfig,
    item: VocabularyItem,
    chain: ProviderChain,
    prompts: PromptLibrary,
    *,
    sense: str = "",
) -> tuple[EntryDraft, Completion]:
    """Write the three student-facing fields for one item.

    The window is built from the item's own locator, so it is centred on the
    passage being defined and bounded: a book whose paragraph assembly merged
    six pages into one block cannot make this request carry six pages of it.
    """
    window = context_for_locator(
        document,
        item.locator,
        paragraphs_before=CONTEXT_PARAGRAPHS,
        paragraphs_after=CONTEXT_PARAGRAPHS,
    )
    rendered = prompts.render(
        "entry",
        audience=job.audience.label,
        book_title=job.book.title or document.title,
        context=window.as_prompt_block(limit=CONTEXT_CHARACTER_LIMIT),
        excerpt=item.excerpt or "",
        sense=sense or "not yet determined",
        term=item.term,
    )
    return generate_structured(
        chain,
        [
            Message(role="system", content=rendered.system),
            Message(role="user", content=rendered.user),
        ],
        EntryDraft,
    )


def apply_draft(
    item: VocabularyItem, draft: EntryDraft, completion: Completion
) -> None:
    """Attach a draft to an item, recording which model wrote it.

    The three fields assigned here are the only ones a model's words ever reach.
    The excerpt and the chapter reference are not among them, and there is no
    branch in this function that could make them so.
    """
    item.definition = draft.definition.strip()
    item.korean_meaning = draft.korean_meaning.strip()
    item.excerpt_context = draft.excerpt_context.strip()
    item.provenance.generator_provider = completion.provider
    item.provenance.generator_model = completion.model
