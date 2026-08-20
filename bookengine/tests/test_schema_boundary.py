"""The one rule, checked where it is actually enforced.

A model may say which word is worth teaching, which of the book's sentences
teaches it best, and what the word means. It may not say what the book says, and
it may not say which chapter a passage came from — both of those are cut from
the source, and the reason a fabricated quotation cannot reach a workbook is not
that something catches it but that there is no field to put it in.

That claim lives in `schemas.py`. These tests hold it there, so that adding an
`excerpt` field to a response model breaks a test rather than quietly becoming a
supported feature.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from bookengine.source.excerpt import ExcerptLocator
from bookengine.vocabulary import schemas
from bookengine.vocabulary.models import VocabularyItem

# Every shape the engine will accept an answer in.
RESPONSE_MODELS = [
    schemas.CandidateWord,
    schemas.CandidateList,
    schemas.RankedWord,
    schemas.RankedList,
    schemas.OccurrenceChoice,
    schemas.EntryDraft,
    schemas.AuditItemVerdict,
    schemas.AuditReport,
]

# Names a field carrying book text or a chapter number would plausibly have.
FORBIDDEN_FIELDS = {
    "excerpt",
    "quote",
    "quotation",
    "passage",
    "sentence",
    "book_excerpt",
    "bookexcerpt",
    "text",
    "chapter",
    "chapter_reference",
    "chapternumber",
    "chapter_number",
    "page",
    "char_start",
    "char_end",
    "locator",
}


@pytest.mark.parametrize("model", RESPONSE_MODELS, ids=lambda m: m.__name__)
def test_no_response_model_has_a_field_for_book_text_or_a_chapter(model):
    assert set(model.model_fields) & FORBIDDEN_FIELDS == set()


@pytest.mark.parametrize("model", RESPONSE_MODELS, ids=lambda m: m.__name__)
def test_every_response_model_refuses_fields_it_did_not_ask_for(model):
    """`extra="forbid"` is what stops an unused extra field becoming a used one."""
    assert model.model_config.get("extra") == "forbid"


def test_a_model_volunteering_a_quotation_has_its_whole_answer_refused():
    """Not half-accepted, and not accepted-with-the-extra-ignored."""
    with pytest.raises(ValidationError):
        schemas.EntryDraft(
            definition="a difficult situation",
            korean_meaning="곤경",
            excerpt_context="Mara is left in the hut.",
            excerpt="Mara set the whole maze alight.",
        )


def test_a_model_volunteering_a_chapter_number_has_its_answer_refused():
    with pytest.raises(ValidationError):
        schemas.EntryDraft(
            definition="a difficult situation",
            korean_meaning="곤경",
            excerpt_context="Mara is left in the hut.",
            chapter=14,
        )


def test_choosing_an_occurrence_is_choosing_an_integer():
    """The whole interface a model has to the book's text at this stage."""
    assert set(schemas.OccurrenceChoice.model_fields) == {"index", "reason"}


def test_the_generated_schema_sent_to_a_provider_carries_no_such_field():
    """The models are one thing; what a provider is told to enforce is another."""
    for model in RESPONSE_MODELS:
        rendered = repr(schemas.json_schema_for(model))
        for name in ("excerpt", "chapter_reference", "char_start"):
            assert f"'{name}'" not in rendered


def test_a_chapter_reference_has_no_setter_to_be_written_through():
    """It is derived from the locator on every read, so it cannot be assigned."""
    item = VocabularyItem(lesson=1, term="reluctant", normalized_term="reluctant")
    item.locator = ExcerptLocator(chapter=7, char_start=0, char_end=10)

    assert item.chapter_reference == "Chapter 7"
    with pytest.raises(AttributeError):
        item.chapter_reference = "Chapter 14"
