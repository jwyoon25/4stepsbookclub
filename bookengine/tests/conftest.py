"""Shared fixtures: one fixture book, built once, and a job that uses it."""

from __future__ import annotations

from pathlib import Path

import pytest

from bookengine.config import JobConfig
from bookengine.source.document import BookDocument
from bookengine.source.ingest import ingest_book
from fixtures.prose import chapter_specs
from fixtures.synthetic_book import render_book


@pytest.fixture(scope="session")
def book_path(tmp_path_factory) -> Path:
    """A twelve-chapter novel, rendered once for the whole suite."""
    path = tmp_path_factory.mktemp("books") / "the-hollow-road.pdf"
    render_book(path, chapters=chapter_specs(12))
    return path


@pytest.fixture(scope="session")
def document(book_path: Path) -> BookDocument:
    return ingest_book(book_path, title="The Hollow Road").document


def build_job(book_path: Path, output: Path, **overrides) -> JobConfig:
    """A job over the fixture book, with sane defaults every test can adjust."""
    payload = {
        "book": {"path": str(book_path), "title": "The Hollow Road"},
        "audience": {"grade_min": 7, "grade_max": 8},
        "vocabulary_per_lesson": 4,
        "candidates_per_lesson": 20,
        "lessons": [
            {"lesson": 1, "start_chapter": 1, "end_chapter": 6},
            {"lesson": 2, "start_chapter": 7, "end_chapter": 12},
        ],
        "llm": {
            "generator": {"provider": "fake", "model": "generator-1"},
            "auditor": {"provider": "fake", "model": "auditor-1"},
        },
        "output": {"directory": str(output)},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(payload.get(key), dict):
            payload[key].update(value)
        else:
            payload[key] = value
    return JobConfig.model_validate(payload)


@pytest.fixture
def job(book_path: Path, tmp_path: Path) -> JobConfig:
    return build_job(book_path, tmp_path / "output")
