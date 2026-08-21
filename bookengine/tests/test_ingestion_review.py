"""When a chapter map has to be looked at by a person before it is used.

Chapter assignment is the one workbook fact nothing downstream can check. Every
quotation can be real, every word can occur where it says, and the whole book
can still be filed one chapter off — there is no later stage that would notice.

Detection already refuses a map it cannot make sense of. These tests are about
the middle case: a map that parsed, that looks wrong in a way only a person
holding the book can settle, and that used to be a note printed above a run
that carried on regardless.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bookengine.source.approval import (
    ApprovalStore,
    chapter_fingerprint,
)
from bookengine.source.cache import ParseCache
from bookengine.source.ingest import (
    INGESTION_PASS,
    INGESTION_REVIEW_REQUIRED,
    ingest_book,
)
from fixtures.prose import chapter_specs
from fixtures.synthetic_book import render_book


@pytest.fixture(scope="module")
def ordinary(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("review") / "ordinary.pdf"
    render_book(path, chapters=chapter_specs(8))
    return path


@pytest.fixture(scope="module")
def suspicious(tmp_path_factory) -> Path:
    """A book with a chapter that is one word long.

    That is what a heading matched inside the prose looks like from here, and
    nothing downstream would notice: the quotations would all be real and all
    be filed under the wrong number.
    """
    chapters = chapter_specs(8)
    chapters[4].paragraphs = ["Short."]
    path = tmp_path_factory.mktemp("review") / "suspicious.pdf"
    render_book(path, chapters=chapters)
    return path


# --- the status ------------------------------------------------------------


def test_an_ordinary_book_ingests_pass(ordinary):
    report = ingest_book(ordinary, cache=None, use_cache=False)

    assert report.status == INGESTION_PASS
    assert report.concerns == []
    assert not report.needs_review


def test_a_book_with_a_one_word_chapter_needs_review(suspicious):
    report = ingest_book(suspicious, cache=None, use_cache=False)

    assert report.status == INGESTION_REVIEW_REQUIRED
    assert report.needs_review
    assert report.concerns


def test_the_status_is_in_the_rendered_report(suspicious):
    rendered = ingest_book(suspicious, cache=None, use_cache=False).render()

    assert INGESTION_REVIEW_REQUIRED in rendered
    assert "A person has to check these before generating" in rendered


def test_concerns_are_kept_apart_from_notes(suspicious):
    """A note is worth knowing. A concern stops a run. Mixing them loses that."""
    report = ingest_book(suspicious, cache=None, use_cache=False)

    assert set(report.concerns).isdisjoint(report.notes)


def test_a_cached_parse_raises_the_same_concerns_as_a_fresh_one(
    suspicious, tmp_path
):
    """The regression: the second run reported PASS and walked past the gate.

    One of the concerns was computed from the extraction rather than from the
    document, and a cache hit has no extraction — so re-running the same book
    silently cleared its own review requirement.
    """
    cache = ParseCache(directory=tmp_path / "cache")
    fresh = ingest_book(suspicious, cache=cache)
    cached = ingest_book(suspicious, cache=cache)

    assert cached.from_cache
    assert cached.status == fresh.status == INGESTION_REVIEW_REQUIRED
    assert cached.concerns == fresh.concerns


# --- the approval ----------------------------------------------------------


def test_an_approval_covers_the_map_it_was_given_for(suspicious, tmp_path):
    document = ingest_book(suspicious, cache=None, use_cache=False).document
    store = ApprovalStore(directory=tmp_path / "cache")

    assert store.find(document) is None
    store.record(document, ["chapter 5 is one word long"])
    assert store.find(document) is not None


def test_an_approval_records_what_was_actually_signed_off(suspicious, tmp_path):
    """So a later reader sees the list, not an unqualified "approved"."""
    report = ingest_book(suspicious, cache=None, use_cache=False)
    store = ApprovalStore(directory=tmp_path / "cache")

    approval = store.record(report.document, report.concerns)

    assert approval.reviewed == report.concerns
    assert approval.chapters == len(report.document.chapters)


def test_an_approval_does_not_carry_over_to_a_different_chapter_map(
    suspicious, tmp_path
):
    """A changed ingester must ask again rather than inherit old confidence."""
    document = ingest_book(suspicious, cache=None, use_cache=False).document
    store = ApprovalStore(directory=tmp_path / "cache")
    approval = store.record(document, [])

    # The kind of difference a changed paragraph assembler would produce.
    document.chapters[0].page_start += 1

    assert chapter_fingerprint(document) != approval.fingerprint
    assert store.find(document) is None


def test_an_approval_does_not_carry_over_to_another_book(
    suspicious, ordinary, tmp_path
):
    store = ApprovalStore(directory=tmp_path / "cache")
    store.record(ingest_book(suspicious, cache=None, use_cache=False).document, [])

    other = ingest_book(ordinary, cache=None, use_cache=False).document

    assert store.find(other) is None


def test_a_damaged_approvals_file_costs_a_review_rather_than_granting_one(
    suspicious, tmp_path
):
    """Failing open here would be the wrong direction."""
    document = ingest_book(suspicious, cache=None, use_cache=False).document
    store = ApprovalStore(directory=tmp_path / "cache")
    store.record(document, [])

    store.path.write_text("{ not json", encoding="utf-8")

    assert store.find(document) is None


def test_an_approval_can_be_withdrawn(suspicious, tmp_path):
    document = ingest_book(suspicious, cache=None, use_cache=False).document
    store = ApprovalStore(directory=tmp_path / "cache")
    store.record(document, [])

    assert store.forget(document.content_hash) is True
    assert store.find(document) is None
    assert store.forget(document.content_hash) is False


# --- the gate the CLI puts in front of a run -------------------------------


def run_cli(*arguments: str) -> int:
    from bookengine.cli import main

    return main(list(arguments))


def test_ingest_exits_nonzero_on_a_book_nobody_has_reviewed(
    suspicious, tmp_path, capsys
):
    code = run_cli(
        "ingest", "--book", str(suspicious), "--cache", str(tmp_path / "cache")
    )

    assert code != 0
    assert "--approve" in capsys.readouterr().out


def test_approving_it_makes_the_next_ingest_succeed(suspicious, tmp_path, capsys):
    cache = str(tmp_path / "cache")
    approved = run_cli(
        "ingest", "--book", str(suspicious), "--cache", cache, "--approve"
    )
    assert approved == 0
    capsys.readouterr()

    assert run_cli("ingest", "--book", str(suspicious), "--cache", cache) == 0
    assert "was approved on" in capsys.readouterr().out


def test_there_is_nothing_to_approve_on_a_clean_book(ordinary, tmp_path, capsys):
    """An approval that can be given without reading anything is worth nothing."""
    code = run_cli(
        "ingest",
        "--book",
        str(ordinary),
        "--cache",
        str(tmp_path / "cache"),
        "--approve",
    )

    assert code == 0
    assert "Nothing to approve" in capsys.readouterr().out
    assert not (tmp_path / "cache" / "approvals.json").exists()


# --- what a cached report is allowed to forget -----------------------------


def test_a_cached_report_names_the_furniture_a_fresh_one_names(ordinary, tmp_path):
    """The regression: `_from_cache` built a report with no furniture at all.

    The count survived the cache in `stats`, so a second run said three hundred
    lines had been removed and could not name one of them. The records now live
    on the document, which is the thing the cache stores, and the report reads
    them from there — so the two paths cannot answer differently.
    """
    cache = ParseCache(directory=tmp_path / "cache")
    fresh = ingest_book(ordinary, cache=cache)
    cached = ingest_book(ordinary, cache=cache)

    assert fresh.from_cache is False
    assert cached.from_cache is True
    assert fresh.furniture, "the fixture book has running heads to find"
    assert cached.furniture == fresh.furniture


def test_the_furniture_line_of_the_report_reads_the_same_either_way(
    ordinary, tmp_path
):
    """Same numbers, same examples, same sentence."""
    cache = ParseCache(directory=tmp_path / "cache")
    fresh = ingest_book(ordinary, cache=cache).render()
    cached = ingest_book(ordinary, cache=cache).render()

    def furniture_line(rendered: str) -> str:
        return next(
            line for line in rendered.splitlines() if line.startswith("Running heads")
        )

    assert furniture_line(cached) == furniture_line(fresh)
    assert "none found" not in furniture_line(cached)


def test_a_cached_document_carries_the_same_furniture_as_a_fresh_parse(
    ordinary, tmp_path
):
    """Serialised and read back, record for record."""
    cache = ParseCache(directory=tmp_path / "cache")
    fresh = ingest_book(ordinary, cache=cache).document
    cached = ingest_book(ordinary, cache=cache).document

    assert cached.furniture == fresh.furniture
    assert cached.stats.furniture_lines_dropped == fresh.stats.furniture_lines_dropped
    assert all(record.pages > 0 and record.example for record in cached.furniture)
