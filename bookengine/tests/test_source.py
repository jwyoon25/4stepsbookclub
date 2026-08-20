"""Ingestion: what came out of the PDF against what went into it."""

from __future__ import annotations

import pytest

from bookengine.errors import UnsupportedBookError
from bookengine.source import layout
from bookengine.source.cache import ParseCache
from bookengine.source.document import build_document
from bookengine.source.ingest import ingest_book
from bookengine.source.pdf import extract_pdf
from bookengine.source.search import context_window, find_occurrences
from bookengine.source.text import normalize_for_matching
from fixtures.prose import chapter_specs
from fixtures.synthetic_book import render_book


def test_every_paragraph_survives_the_round_trip(tmp_path):
    """The strongest available check: the PDF gives back what was written."""
    specs = chapter_specs(6)
    path = tmp_path / "round-trip.pdf"
    render_book(path, chapters=specs)

    book = extract_pdf(path)
    furniture = layout.detect_furniture(book)
    lines = layout.prose_lines(book, furniture)
    paragraphs = layout.assemble_paragraphs(lines, layout.page_metrics(lines))

    rebuilt = {normalize_for_matching(entry.text) for entry in paragraphs}
    for chapter in specs:
        for written in chapter.paragraphs:
            assert normalize_for_matching(written) in rebuilt


def test_running_heads_and_folios_are_not_prose(tmp_path):
    path = tmp_path / "furniture.pdf"
    render_book(path, chapters=chapter_specs(6), running_header="THE HOLLOW ROAD")

    book = extract_pdf(path)
    furniture = layout.detect_furniture(book)
    signatures = {record.signature for record in furniture.records}

    assert "THE HOLLOW ROAD" in signatures
    assert "#" in signatures
    for line in layout.prose_lines(book, furniture):
        assert "HOLLOW ROAD" not in line.text.upper()


def test_a_word_broken_across_a_line_is_findable_again(tmp_path):
    path = tmp_path / "hyphens.pdf"
    render_book(path, chapters=chapter_specs(6), hyphenate=True)
    document = ingest_book(path, title="The Hollow Road").document

    assert document.stats.hyphen_repairs > 0
    assert find_occurrences(document, "incomprehensible")


def test_document_offsets_describe_the_text_they_claim_to(document):
    for chapter in document.chapters:
        for paragraph in chapter.paragraphs:
            text = chapter.text[paragraph.char_start : paragraph.char_end]
            assert text == text.strip()
            assert text
        for sentence in chapter.sentences:
            text = chapter.text[sentence.char_start : sentence.char_end]
            assert text == text.strip()
            assert "\n\n" not in text


def test_source_ids_are_unique_across_the_book(document):
    ids = [
        sentence.id
        for chapter in document.chapters
        for sentence in chapter.sentences
    ]
    assert len(ids) == len(set(ids))


def test_chapter_headings_are_not_part_of_the_chapter_text(document):
    for chapter in document.chapters:
        assert not chapter.text.upper().startswith("CHAPTER")


def test_occurrence_search_respects_the_lesson_s_chapter_range(document):
    everywhere = {entry.chapter for entry in find_occurrences(document, "predicament")}
    early = {
        entry.chapter
        for entry in find_occurrences(document, "predicament", chapters=range(1, 7))
    }
    assert early
    assert early < everywhere


def test_the_context_window_is_real_neighbouring_prose(document):
    occurrence = find_occurrences(document, "predicament")[0]
    window = context_window(document, occurrence)
    chapter = document.chapter(occurrence.chapter)

    assert normalize_for_matching(window.passage) in chapter.normalized
    if window.after:
        assert normalize_for_matching(window.after) in chapter.normalized


def test_an_image_only_book_is_refused_rather_than_guessed_at(tmp_path):
    import pymupdf

    document = pymupdf.open()
    for _ in range(6):
        document.new_page(width=300, height=400)
    path = tmp_path / "scan.pdf"
    document.save(path)
    document.close()

    with pytest.raises(UnsupportedBookError) as failure:
        extract_pdf(path)
    assert "image-only scan" in str(failure.value)


def test_the_cache_returns_the_same_document_it_stored(book_path, tmp_path):
    cache = ParseCache(directory=tmp_path / "cache")
    first = ingest_book(book_path, cache=cache)
    second = ingest_book(book_path, cache=cache)

    assert not first.from_cache
    assert second.from_cache
    assert [c.text for c in second.document.chapters] == [
        c.text for c in first.document.chapters
    ]


def test_a_cache_entry_from_an_older_parser_is_ignored(book_path, tmp_path):
    import json

    cache = ParseCache(directory=tmp_path / "cache")
    report = ingest_book(book_path, cache=cache)
    path = cache.path_for(report.document.content_hash)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cache_format_version"] = payload.get("cache_format_version", 1) + 99
    payload["version"] = payload.get("version", 1) + 99
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert not ingest_book(book_path, cache=cache).from_cache


def test_a_document_can_be_built_without_a_cache_and_matches(book_path):
    book = extract_pdf(book_path)
    furniture = layout.detect_furniture(book)
    lines = layout.prose_lines(book, furniture)
    metrics = layout.page_metrics(lines)
    from bookengine.source.chapters import detect_chapters

    built = build_document(
        book, detect_chapters(lines), lines, metrics, title="The Hollow Road"
    )
    assert built.chapter_numbers == list(range(1, 13))
