"""The run, end to end, against a model that is not trying to be helpful.

These are the tests that matter. Each of them takes one of the failures the
design claims to make impossible and has the fake model commit it, then asserts
that nothing wrong reached a `READY` row. A test that only checks the happy path
would pass just as well against a design with no verification in it at all.
"""

from __future__ import annotations

import json

import pytest

from bookengine.export import render_tsv, write_audit_json, write_tsv
from bookengine.export.workbook_contract import VOCABULARY_COLUMNS
from bookengine.llm.chain import ProviderChain
from bookengine.prompts import PromptLibrary
from bookengine.source.excerpt import verify_excerpt
from bookengine.source.text import normalize_for_matching, normalize_term
from bookengine.vocabulary.models import Status
from bookengine.vocabulary.pipeline import run_job
from conftest import build_job
from fakes import ScriptedProvider


def run(document, job, provider=None, auditor=None):
    """One run against scripted endpoints, with the two roles kept apart.

    The auditor is a twin of the generator rather than the same object: same
    scripted behaviour, different provider identity. The engine reads
    independence off the completions that came back, so one object answering
    both would make every test a test of a run that audited its own work.
    """
    writer = provider or ScriptedProvider()
    generator = ProviderChain(providers=[writer])
    audit_chain = ProviderChain(providers=[auditor or writer.as_auditor()])
    return run_job(document, job, generator, audit_chain, PromptLibrary())


def test_a_clean_run_fills_every_lesson(document, job):
    result = run(document, job)

    assert result.ok, result.report.render()
    assert result.report.ready_total == job.total_requested
    for lesson in result.report.lessons:
        assert lesson.ready == job.vocabulary_per_lesson


def test_every_ready_quotation_is_the_book_s_own_words(document, job):
    result = run(document, job)

    assert result.ready
    for item in result.ready:
        verification = verify_excerpt(
            document, item.locator, item.excerpt, term=item.term
        )
        assert verification.ok, verification.reasons
        chapter = document.chapter(item.locator.chapter)
        assert normalize_for_matching(item.excerpt) in chapter.normalized


def test_chapter_references_come_from_the_source_map(document, job):
    result = run(document, job)

    for item in result.ready:
        lesson = job.lesson(item.lesson)
        assert item.chapter_reference == f"Chapter {item.locator.chapter}"
        assert item.locator.chapter in lesson.chapters


def test_no_word_is_taught_twice_anywhere_in_the_book(document, job):
    result = run(document, job)

    keys = [normalize_term(item.term) for item in result.ready]
    assert len(keys) == len(set(keys))
    assert result.report.duplicate_conflicts == []


def test_every_ready_word_occurs_in_its_own_lesson_s_chapters(document, job):
    from bookengine.source.search import occurs_in_chapters

    result = run(document, job)

    for item in result.ready:
        assert occurs_in_chapters(document, item.term, job.lesson(item.lesson).chapters)


def test_a_model_that_picks_a_nonexistent_passage_still_gets_a_real_quote(
    document, job
):
    """A bad index costs a better ranking, not the guarantee."""
    result = run(document, job, ScriptedProvider(bad_occurrence_index=True))

    assert result.ok, result.report.render()
    for item in result.ready:
        assert verify_excerpt(document, item.locator, item.excerpt).ok


def test_an_audit_failure_replaces_the_item_rather_than_shipping_it(document, job):
    result = run(document, job, ScriptedProvider(fail_audit={"predicament"}))

    assert result.ok, result.report.render()
    assert "predicament" not in {normalize_term(i.term) for i in result.ready}
    rejected = [
        item
        for item in result.items
        if normalize_term(item.term) == "predicament"
    ]
    assert rejected and rejected[0].status is Status.FAILED
    assert result.stats.replacements >= 1


def test_an_item_with_no_audit_verdict_cannot_become_ready(document, job):
    """A truncated auditor reply must not read as approval."""
    provider = ScriptedProvider()
    # An auditor that never answers in the requested shape returns no verdicts.
    auditor = ScriptedProvider(name="silent", malformed_first=10_000)
    result = run(document, job, provider, auditor)

    assert not result.ok
    assert result.report.ready_total == 0
    assert all(item.status is not Status.READY for item in result.items)


def test_a_lesson_that_cannot_be_filled_fails_loudly(document, book_path, tmp_path):
    """Twenty words from a pool the model rejects entirely is a failed run."""
    job = build_job(book_path, tmp_path / "out", vocabulary_per_lesson=6)
    provider = ScriptedProvider(exclusion_risk=5)
    result = run(document, job, provider)

    assert not result.ok
    message = result.report.render()
    assert "could not reach" in message
    assert "Generation was not marked successful" in message


def test_only_ready_rows_are_exported(document, job, tmp_path):
    result = run(document, job, ScriptedProvider(fail_audit={"predicament"}))

    text = render_tsv(result.items)
    lines = text.splitlines()
    assert all(len(line.split("\t")) == len(VOCABULARY_COLUMNS) for line in lines)
    assert len(lines) == result.report.ready_total
    assert "predicament\t" not in text


def test_the_paste_block_survives_a_round_trip_through_a_grid(document, job, tmp_path):
    """Splitting the file the way a spreadsheet does must give back the cells."""
    result = run(document, job)
    path = write_tsv(result.items, tmp_path / "vocabulary.tsv")
    text = path.read_text(encoding="utf-8")

    rows = [line.split("\t") for line in text.splitlines()]
    assert all(len(row) == len(VOCABULARY_COLUMNS) for row in rows)

    excerpt_column = VOCABULARY_COLUMNS.index("Excerpt from the book")
    for row in rows[1:]:
        chapter = document.chapter(int(row[-1].removeprefix("Chapter ").strip()))
        assert normalize_for_matching(row[excerpt_column]) in chapter.normalized


def test_the_audit_artifact_records_what_actually_happened(document, job, tmp_path):
    result = run(document, job)
    path = write_audit_json(
        result.items,
        tmp_path / "audit.json",
        job=job,
        document=document,
        run=result.stats.as_dict(),
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["ready_items"] == result.report.ready_total
    assert payload["requested_items"] == job.total_requested
    assert payload["duplicate_count"] == 0
    assert payload["exact_quote_checks"]["failed"] == 0
    assert payload["chapter_checks"]["failed"] == 0


@pytest.mark.parametrize("policy", ["exact", "lemma"])
def test_both_duplicate_policies_still_forbid_the_same_word_twice(
    document, book_path, tmp_path, policy
):
    job = build_job(book_path, tmp_path / "out", dedupe={"policy": policy})
    result = run(document, job)

    keys = [normalize_term(item.term) for item in result.ready]
    assert len(keys) == len(set(keys))
