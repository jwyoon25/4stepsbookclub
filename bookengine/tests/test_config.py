"""The job file: what it accepts, and what it refuses before a book is opened."""

from __future__ import annotations

import pytest
import yaml

from bookengine.config import JobConfig, load_job, validate_lessons_against_book
from bookengine.errors import ConfigError
from conftest import build_job

BASE = {
    "book": {"path": "book.pdf"},
    "audience": {"grade_min": 7, "grade_max": 8},
    "lessons": [{"lesson": 1, "start_chapter": 1, "end_chapter": 12}],
    "llm": {
        "generator": {"provider": "groq", "model": "a"},
        "auditor": {"provider": "nvidia", "model": "b"},
    },
}


def job_with(**changes):
    payload = {**BASE, **changes}
    return JobConfig.model_validate(payload)


def test_a_minimal_job_validates_and_takes_the_documented_defaults():
    job = job_with()
    assert job.vocabulary_per_lesson == 20
    assert job.dedupe.policy == "lemma"
    assert job.excerpt.max_characters == 600
    assert job.candidates.mode == "harvest"


def test_overlapping_lessons_are_refused():
    with pytest.raises(ValueError, match="overlap"):
        job_with(
            lessons=[
                {"lesson": 1, "start_chapter": 1, "end_chapter": 12},
                {"lesson": 2, "start_chapter": 10, "end_chapter": 20},
            ]
        )


def test_repeated_lesson_numbers_are_refused():
    with pytest.raises(ValueError, match="unique"):
        job_with(
            lessons=[
                {"lesson": 1, "start_chapter": 1, "end_chapter": 5},
                {"lesson": 1, "start_chapter": 6, "end_chapter": 10},
            ]
        )


def test_a_backwards_chapter_range_is_refused():
    with pytest.raises(ValueError, match="ends at chapter"):
        job_with(lessons=[{"lesson": 1, "start_chapter": 12, "end_chapter": 3}])


def test_a_pool_smaller_than_the_target_is_refused():
    with pytest.raises(ValueError, match="nothing to replace"):
        job_with(vocabulary_per_lesson=20, candidates_per_lesson=10)


def test_an_unknown_setting_is_refused_rather_than_ignored():
    with pytest.raises(ValueError):
        job_with(vocabluary_per_lesson=20)


def test_a_lesson_referring_to_a_chapter_the_book_lacks_stops_the_run(
    book_path, tmp_path
):
    job = build_job(
        book_path,
        tmp_path / "out",
        lessons=[{"lesson": 1, "start_chapter": 1, "end_chapter": 62}],
    )
    with pytest.raises(ConfigError) as failure:
        validate_lessons_against_book(job, list(range(1, 13)))
    message = str(failure.value)
    assert "Lesson 1 covers Chapters 1-62" in message
    assert "no chapter 13" in message


def test_chapters_left_out_of_the_plan_are_a_note_not_a_failure(book_path, tmp_path):
    job = build_job(
        book_path,
        tmp_path / "out",
        lessons=[{"lesson": 1, "start_chapter": 1, "end_chapter": 6}],
    )
    notes = validate_lessons_against_book(job, list(range(1, 13)))
    assert any("in no lesson" in note for note in notes)


def test_model_names_come_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("GENERATOR_MODEL", "llama-3.3-70b")
    payload = {**BASE}
    payload["llm"] = {
        "generator": {"provider": "groq", "model": "${GENERATOR_MODEL}"},
        "auditor": {"provider": "nvidia", "model": "${AUDITOR_MODEL:-fallback-model}"},
    }
    path = tmp_path / "job.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    job = load_job(path)
    assert job.llm.generator.model == "llama-3.3-70b"
    assert job.llm.auditor.model == "fallback-model"


def test_an_unset_variable_with_no_default_is_named_in_the_error(tmp_path):
    payload = {**BASE}
    payload["llm"] = {
        "generator": {"provider": "groq", "model": "${DEFINITELY_NOT_SET_12345}"},
        "auditor": {"provider": "nvidia", "model": "b"},
    }
    path = tmp_path / "job.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    with pytest.raises(ConfigError, match="DEFINITELY_NOT_SET_12345"):
        load_job(path)


def test_paths_resolve_against_the_job_file(tmp_path):
    (tmp_path / "sources").mkdir()
    payload = {**BASE, "book": {"path": "sources/the-book.pdf"}}
    path = tmp_path / "job.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")

    job = load_job(path)
    assert job.book.path == tmp_path / "sources" / "the-book.pdf"
    assert job.book.title == "the book"


def test_a_shared_generator_and_auditor_is_flagged():
    shared = {"provider": "groq", "model": "same"}
    job = job_with(llm={"generator": shared, "auditor": dict(shared)})
    assert not job.llm.audit_is_independent
