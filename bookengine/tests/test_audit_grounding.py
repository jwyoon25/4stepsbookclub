"""What the auditor is shown, and what it can therefore catch.

`context_accuracy` asks whether a sentence describes what is happening in the
book. That is only a question if the auditor can see what is happening in the
book. Given the excerpt alone, "Mara discovers that Alder has betrayed her" is
neither supported nor contradicted by two sentences about a bed in a hut — so a
model would answer it from whatever it remembers of the novel, which is the one
source this engine refuses to accept.

These tests are about the material, not about the model. They check that the
paragraphs really are in the request, that they are the book's own, and that an
auditor which reads them rejects a claim they do not show.
"""

from __future__ import annotations

import pytest

from bookengine.config import ExcerptConfig, JobConfig
from bookengine.llm.chain import ProviderChain
from bookengine.prompts import PromptLibrary
from bookengine.source.document import BookDocument
from bookengine.source.search import find_occurrences
from bookengine.vocabulary.audit import (
    CONTEXT_CHARACTER_BUDGET,
    NO_CONTEXT,
    _render_item,
    apply_verdicts,
    audit_batch,
)
from bookengine.vocabulary.models import Status, VocabularyItem
from bookengine.vocabulary.quotes import build_excerpt
from fakes import GroundedAuditor

# A claim that reads like this book and is nowhere in it. The surrounding
# paragraphs are about a bed, a tally scratched into a beam, and the settlement
# starting its morning; nothing in them is a betrayal or a burning.
FALSE_CLAIM = "Mara discovers Alder betrayed her and burns the settlement down."


def item_for(document: BookDocument, term: str, chapters: range) -> VocabularyItem:
    """A finished item built the way the pipeline builds one."""
    occurrences = find_occurrences(document, term, chapters=chapters)
    assert occurrences, f"{term!r} is not in the fixture book's {chapters}"
    candidate = build_excerpt(document, occurrences[0], ExcerptConfig())
    assert candidate is not None

    item = VocabularyItem(lesson=1, term=term, normalized_term=term)
    item.locator = candidate.locator
    item.excerpt = candidate.text
    item.definition = "a difficult or unpleasant situation."
    item.korean_meaning = "곤경"
    item.excerpt_context = "Mara is left in the hut to consider where she is."
    item.transition(Status.SOURCE_VERIFIED, "test")
    item.transition(Status.GENERATED, "test")
    item.transition(Status.AUDIT_PENDING, "test")
    return item


@pytest.fixture
def audited(document: BookDocument) -> VocabularyItem:
    return item_for(document, "predicament", range(1, 7))


# --- what is in the request ------------------------------------------------


def test_the_auditor_is_sent_the_paragraph_the_excerpt_was_cut_from(
    document, audited
):
    rendered = _render_item(1, audited, document)
    paragraph = document.chapter(audited.locator.chapter).paragraphs[0]
    passage = document.chapter(audited.locator.chapter).slice(
        paragraph.char_start, paragraph.char_end
    )

    assert "SOURCE CONTEXT" in rendered
    assert passage in rendered
    # More than the excerpt: the paragraph continues past where the quote ends.
    assert len(passage) > len(audited.excerpt)


def test_the_auditor_is_sent_the_neighbouring_paragraphs_too(document, audited):
    chapter = document.chapter(audited.locator.chapter)
    rendered = _render_item(1, audited, document)
    following = chapter.slice(
        chapter.paragraphs[1].char_start, chapter.paragraphs[1].char_end
    )

    assert "[next paragraph]" in rendered
    assert following in rendered


def test_the_source_context_is_the_books_own_text(document, audited):
    """Not a summary, not the model's words — a slice of the chapter."""
    rendered = _render_item(1, audited, document)
    body = rendered.split("SOURCE CONTEXT", 1)[1]
    chapter = document.chapter(audited.locator.chapter)

    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("[", "for entry")):
            continue
        assert stripped in chapter.text


def test_the_context_stays_inside_its_budget(document, audited):
    rendered = _render_item(1, audited, document)
    source = rendered.split("SOURCE CONTEXT for entry 1 (from the book itself):", 1)[1]
    # The three paragraph labels are the only thing over the budget it may add.
    assert len(source) <= CONTEXT_CHARACTER_BUDGET + 200


def test_an_item_with_no_locator_says_so_rather_than_going_quiet(document):
    """An auditor that thinks it has the source and does not is the failure."""
    item = VocabularyItem(lesson=1, term="predicament", normalized_term="predicament")
    item.excerpt_context = "Something happens."

    assert NO_CONTEXT in _render_item(1, item, document)


# --- what that lets the auditor catch --------------------------------------


def audit_with(auditor, items, job, document):
    chain = ProviderChain(providers=[auditor], sleep=lambda _: None)
    return apply_verdicts(
        items, audit_batch(items, job, document, chain, PromptLibrary())
    )


def test_a_plausible_but_unsupported_plot_claim_is_rejected(
    document: BookDocument, job: JobConfig, audited: VocabularyItem
):
    """The excerpt is real, the definition is right, the story is invented.

    Nothing deterministic can catch this: the quotation verifies, the word is
    in it, the chapter is derived. It is caught because the auditor was handed
    the paragraphs the claim is about and they do not show a betrayal.
    """
    audited.excerpt_context = FALSE_CLAIM
    auditor = GroundedAuditor()

    passed, failed = audit_with(auditor, [audited], job, document)

    assert (passed, failed) == ([], [audited])
    assert audited.status is Status.FAILED
    assert audited.audit.context_accuracy == "INACCURATE"
    assert "the context sentence (INACCURATE)" in audited.failures[0]


def test_the_same_item_passes_when_its_context_describes_the_passage(
    document: BookDocument, job: JobConfig, audited: VocabularyItem
):
    """The control. Without it the test above only proves the fake says FAIL."""
    passed, failed = audit_with(GroundedAuditor(), [audited], job, document)

    assert (passed, failed) == ([audited], [])
    assert audited.audit.passed


def test_a_false_claim_fails_even_next_to_sound_entries(
    document: BookDocument, job: JobConfig
):
    """Each entry is judged against its own paragraphs, not the batch's."""
    good = item_for(document, "predicament", range(1, 7))
    bad = item_for(document, "monotonous", range(1, 7))
    bad.excerpt_context = FALSE_CLAIM

    passed, failed = audit_with(GroundedAuditor(), [good, bad], job, document)

    assert passed == [good]
    assert failed == [bad]


def test_the_auditor_has_no_way_to_supply_a_replacement_excerpt(
    document: BookDocument, job: JobConfig, audited: VocabularyItem
):
    """The audit schema has no excerpt field and forbids extras.

    So an auditor cannot rewrite a quotation even by volunteering one: the
    reply is refused as malformed, the batch returns no verdicts, and every
    item in it fails for want of an audit rather than passing with the
    auditor's text.
    """
    excerpt_before = audited.excerpt

    class Meddler(GroundedAuditor):
        def complete(self, messages, **kwargs):
            reply = super().complete(messages, **kwargs)
            payload = reply.text.replace(
                '"notes": null',
                '"notes": null, "excerpt": "Mara set the whole maze alight."',
            )
            return type(reply)(
                text=payload,
                provider=reply.provider,
                model=reply.model,
                prompt_tokens=None,
                completion_tokens=None,
            )

    passed, failed = audit_with(Meddler(), [audited], job, document)

    assert (passed, failed) == ([], [audited])
    assert audited.excerpt == excerpt_before
    assert audited.audit is None
