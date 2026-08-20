"""The prompts, and the structural guarantee that sits underneath them.

The wiring test exists because a prompt is edited by hand and a caller is not:
a renamed placeholder would otherwise be found by a run that reached the model
with `{excerpt}` still in the text.

The schema tests are the more important ones. They assert the property the whole
design rests on — that no model can return a quotation or a chapter number,
because there is no field for one — as a fact about the code rather than as a
claim in a document.
"""

from __future__ import annotations

import pytest

from bookengine.prompts import PromptError, PromptLibrary
from bookengine.vocabulary import schemas

# What each prompt's caller supplies. Kept here rather than derived from the
# files, so that a placeholder renamed in only one of the two places fails.
CALLER_SUPPLIES = {
    "candidates": {
        "audience",
        "book_title",
        "count",
        "excluded_terms",
        "lesson_number",
        "reading_range",
        "source_text",
    },
    "ranking": {"audience", "book_title", "candidates", "reading_range"},
    "occurrence": {"audience", "book_title", "occurrences", "sense", "term"},
    "entry": {"audience", "book_title", "context", "excerpt", "sense", "term"},
    "audit": {"audience", "book_title", "item_count", "items"},
}


@pytest.fixture(scope="module")
def library() -> PromptLibrary:
    return PromptLibrary()


@pytest.mark.parametrize("name", sorted(CALLER_SUPPLIES))
def test_each_prompt_asks_for_exactly_what_its_caller_supplies(library, name):
    assert library.placeholders(name) == CALLER_SUPPLIES[name]


@pytest.mark.parametrize("name", sorted(CALLER_SUPPLIES))
def test_each_prompt_renders_and_leaves_nothing_unfilled(library, name):
    rendered = library.render(name, **dict.fromkeys(CALLER_SUPPLIES[name], "VALUE"))
    assert rendered.user.strip()
    assert rendered.system.strip()
    assert "{" not in rendered.user or "}" not in rendered.user.split("{")[-1][:80]


def test_a_missing_value_is_an_error_rather_than_a_gap(library):
    with pytest.raises(PromptError, match="excerpt"):
        library.render("entry", audience="a", book_title="b", term="c", sense="d")


def test_the_auditor_is_told_it_did_not_write_the_list(library):
    """The framing is what separates an audit from asking a model to agree."""
    text = library.render(
        "audit", audience="a", book_title="b", item_count=1, items="x"
    ).user.lower()
    assert "did not create" in text or "another system" in text
    assert "find" in text or "error" in text


# --- the structural guarantee ---------------------------------------------

FORBIDDEN = {
    "excerpt",
    "quote",
    "quotation",
    "passage",
    "chapter",
    "chapter_reference",
    "page",
    "text",
    "source",
}

ANSWER_MODELS = [
    schemas.CandidateWord,
    schemas.CandidateList,
    schemas.RankedWord,
    schemas.RankedList,
    schemas.OccurrenceChoice,
    schemas.EntryDraft,
    schemas.AuditItemVerdict,
    schemas.AuditReport,
]


@pytest.mark.parametrize("model", ANSWER_MODELS, ids=lambda m: m.__name__)
def test_no_model_answer_can_carry_source_material(model):
    """A model has nowhere to put a quotation, a chapter, or a page number.

    `excerpt_context` is allowed: it is the model's own sentence about the
    story, not a claim about what the book says verbatim.
    """
    allowed = {"excerpt_context"}
    for name in model.model_fields:
        assert name in allowed or name not in FORBIDDEN, (
            f"{model.__name__}.{name} would let a model return source material."
        )


@pytest.mark.parametrize("model", ANSWER_MODELS, ids=lambda m: m.__name__)
def test_an_unexpected_field_is_refused_rather_than_ignored(model):
    """`extra="forbid"` is what stops an unused field becoming a used one."""
    assert model.model_config.get("extra") == "forbid"


def test_choosing_an_occurrence_is_choosing_a_number():
    fields = schemas.OccurrenceChoice.model_fields
    assert set(fields) == {"index", "reason"}
    assert fields["index"].annotation is int


def test_the_response_schemas_survive_being_flattened_for_a_provider():
    """Several free endpoints reject `$ref`, so the schema must inline."""
    for model in ANSWER_MODELS:
        schema = schemas.json_schema_for(model)
        assert "$defs" not in schema
        assert "$ref" not in str(schema)
