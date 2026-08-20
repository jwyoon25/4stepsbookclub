"""The command line, which is the whole product for now.

Two commands. `ingest` reads a book and reports what it found without asking a
model anything, which is what an operator runs first on a new PDF and the only
thing they need to run to find out whether a book is usable at all. `vocab`
does the run.

The output is a column of stages with a verdict beside each, because the useful
question during a five-minute run is "which stage is this failing at". And a
failure prints what would have to change: which lesson came up short, how short,
and why the missing items were rejected. "Error." is not a report.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import JobConfig, load_job, validate_lessons_against_book
from .errors import BookEngineError, ConfigError
from .export import (
    PASTE_TARGET,
    VOCABULARY_SHEET_NAME,
    write_audit_json,
    write_tsv,
    write_vocabulary_json,
)
from .llm.registry import build_chains
from .prompts import PromptLibrary
from .source.approval import ApprovalStore
from .source.cache import ParseCache
from .source.ingest import ingest_book
from .vocabulary.pipeline import Progress, RunResult, run_job

BANNER = "4Steps Vocabulary Generator"
_LABEL_WIDTH = 30

EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_USAGE = 2


def _line(label: str, value: str) -> str:
    return f"{label}{'.' * max(1, _LABEL_WIDTH - len(label))} {value}"


class ConsoleProgress(Progress):
    """Stage reporting for a terminal, quiet enough to read at a glance."""

    def __init__(self, stream, verbose: bool) -> None:
        self._stream = stream
        self._verbose = verbose
        self.notes: list[str] = []

    def stage(self, name: str, detail: str = "") -> None:
        if self._verbose:
            print(_line(name, detail or "..."), file=self._stream)

    def note(self, message: str) -> None:
        self.notes.append(message)
        if self._verbose:
            print(f"  note: {message}", file=self._stream)


def _cache_for(directory: Path | None) -> ParseCache | None:
    return None if directory is None else ParseCache(directory=directory)


def _default_cache_directory(job: JobConfig) -> Path:
    return job.output.directory / ".cache"


def command_ingest(arguments: argparse.Namespace) -> int:
    """Read a book and say what is in it, without asking a model anything."""
    cache_directory = None if arguments.no_cache else Path(arguments.cache)
    report = ingest_book(
        arguments.book,
        title=arguments.title,
        expected_chapters=arguments.expected_chapters,
        cache=_cache_for(cache_directory),
        use_cache=not arguments.no_cache,
    )
    print(report.render())

    store = ApprovalStore(directory=Path(arguments.cache))
    if arguments.approve:
        return _record_approval(report, store)

    if report.needs_review:
        existing = store.find(report.document)
        if existing is not None:
            print()
            print(
                f"This chapter map was approved on {existing.approved_at}, so "
                "`vocab` will run against it."
            )
            return EXIT_OK

        print()
        print(
            "Read the chapter listing above against the book itself — the first "
            "chapter, the last, and any flagged above. Then re-run this command "
            "with --approve to record that you have, and `vocab` will accept it."
        )
        return EXIT_INCOMPLETE

    return EXIT_OK


def _record_approval(report, store: ApprovalStore) -> int:
    """Write down that a person has checked this chapter map.

    Refused when there was nothing to check. An approval that could be given
    without reading anything would train everyone to give it, and the value of
    the whole mechanism is that it is only ever asked for when it matters.
    """
    if not report.needs_review:
        print()
        print(
            f"Nothing to approve: this book ingested {report.status} and `vocab` "
            "will run against it as it stands."
        )
        return EXIT_OK

    approval = store.record(report.document, report.concerns)
    print()
    print(
        f"Recorded: {approval.chapters} chapters in {approval.title}, "
        f"reviewed against {len(approval.reviewed)} concern(s)."
    )
    print(f"  {store.path}")
    print(
        "This covers this exact chapter map. Re-parsing the same PDF with a "
        "changed ingester produces a different map and asks again."
    )
    return EXIT_OK


def command_vocab(arguments: argparse.Namespace) -> int:
    """Run a whole job and write its artifacts."""
    job = load_job(arguments.config)
    if arguments.book:
        job.book.path = Path(arguments.book).resolve()
    if arguments.output:
        job.output.directory = Path(arguments.output).resolve()

    print(BANNER)
    print()

    cache_directory = (
        None
        if arguments.no_cache
        else Path(arguments.cache or _default_cache_directory(job))
    )
    ingestion = ingest_book(
        job.book.path,
        title=job.book.title,
        expected_chapters=job.book.expected_chapters,
        cache=_cache_for(cache_directory),
        use_cache=not arguments.no_cache,
    )
    document = ingestion.document
    cached = " (cached)" if ingestion.from_cache else ""
    print(_line("Book ingestion", f"{ingestion.status}{cached}"))
    print(_line("Detected chapters", str(len(document.chapters))))

    approval = _require_review(ingestion, cache_directory)
    if approval is None:
        return EXIT_INCOMPLETE

    notes = validate_lessons_against_book(job, document.chapter_numbers)
    print(_line("Lesson configuration", "PASS"))
    print()

    if arguments.ingest_only:
        print(ingestion.render())
        return EXIT_OK

    generator, auditor = build_chains(
        job.llm,
        cache_directory=None if arguments.no_cache else cache_directory / "llm",
    )
    progress = ConsoleProgress(sys.stdout, verbose=arguments.verbose)
    result = run_job(
        document, job, generator, auditor, PromptLibrary(), progress=progress
    )
    generator.close()
    auditor.close()

    _print_summary(result, job)
    paths = _write_artifacts(result, job, document)

    for note in [*notes, *ingestion.notes, *progress.notes]:
        print(f"  note: {note}")

    if not result.ok:
        print()
        print(result.report.render())
        print()
        print("Artifacts were still written so the run can be inspected:")
        for path in paths:
            print(f"  {path}")
        return EXIT_INCOMPLETE

    print()
    print("Output:")
    for path in paths:
        print(f"  {path}")
    print()
    print(
        f"Paste {paths[0].name} into the {VOCABULARY_SHEET_NAME} tab at "
        f"{PASTE_TARGET}."
    )
    return EXIT_OK


def _require_review(ingestion, cache_directory: Path | None):
    """Stop a run whose chapter map nobody has vouched for.

    Chapter assignment is the one workbook fact nothing downstream can check:
    every quotation can be real and the whole book still filed one chapter off.
    So a suspicious map is a stop rather than a note printed above the output —
    which is what it used to be.

    Returns the approval covering this map, a sentinel meaning none was needed,
    or `None` to refuse.
    """
    if not ingestion.needs_review:
        return _NO_REVIEW_NEEDED

    print()
    print("Ingestion needs a person to look at it before generating:")
    for concern in ingestion.concerns:
        print(f"  - {concern}")

    if cache_directory is None:
        print()
        print(
            "Approvals are kept in the cache directory, and this run has "
            "--no-cache. Run `bookengine ingest --book <pdf> --approve` first, "
            "or drop --no-cache."
        )
        return None

    store = ApprovalStore(directory=cache_directory)
    approval = store.find(ingestion.document)
    if approval is not None:
        print()
        print(f"  approved on {approval.approved_at}; continuing.")
        return approval

    print()
    print(
        "Nobody has confirmed this chapter map. Check the listing against the "
        "book, then record it:"
    )
    print(
        f"  bookengine ingest --book {ingestion.document.source_name} "
        f"--cache {cache_directory} --approve"
    )
    print()
    print(
        "Generation stopped rather than put unchecked chapter numbers on a "
        "workbook page."
    )
    return None


# Returned when no review was required, so that "approved" and "nothing to
# approve" are distinguishable from `None`, which means refuse.
_NO_REVIEW_NEEDED = object()


def _print_summary(result: RunResult, job: JobConfig) -> None:
    report = result.report
    quote_total = report.quote_checks_passed + report.quote_checks_failed
    chapter_total = report.chapter_checks_passed + report.chapter_checks_failed
    audit_total = report.audit_passed + report.audit_failed

    print(_line("Candidate pools", f"{len(result.stats.pools)} lesson(s)"))
    calls = f"{result.stats.llm_calls} ({result.stats.cache_hits} cached)"
    print(_line("Model calls", calls))
    print(_line("Replacements", str(result.stats.replacements)))
    print(
        _line("Validating quotations", f"{report.quote_checks_passed}/{quote_total}")
    )
    print(
        _line("Chapter references", f"{report.chapter_checks_passed}/{chapter_total}")
    )
    print(_line("Checking duplicates", f"{len(report.duplicate_conflicts)} found"))
    print(_line("Independent audit", f"{report.audit_passed}/{audit_total}"))
    independence = report.audit_independence
    print(
        _line(
            "Audit independence",
            f"{independence.get('actual', 'none')} "
            f"(required: {independence.get('required', 'none')})",
        )
    )
    print(_line("Final verification", "PASS" if report.ok else "FAILED"))
    print()
    for lesson in report.lessons:
        mark = "" if lesson.complete else "   <- short"
        print(f"  Lesson {lesson.lesson}: {lesson.ready}/{lesson.requested}{mark}")
    print()
    print(f"READY: {report.ready_total} / {job.total_requested}")
    if report.audit_not_independent:
        print()
        print(
            f"  note: {report.audit_not_independent} row(s) were audited by the "
            "same endpoint that wrote them, so nothing independent checked "
            "them. Both chains reach the same provider — add another endpoint "
            "to `llm.fallbacks`."
        )
    elif result.stats.audit_independence_actual != (
        result.stats.audit_independence_configured
    ):
        print()
        print(
            "  note: the audit was "
            f"{result.stats.audit_independence_actual}-level independent, where "
            f"the job configures {result.stats.audit_independence_configured}. "
            "A provider was down and both chains fell back."
        )


def _write_artifacts(result: RunResult, job: JobConfig, document) -> list[Path]:
    directory = job.output.directory
    tsv = write_tsv(
        result.items,
        directory / job.output.tsv_name,
        include_header=job.output.include_header,
    )
    vocabulary = write_vocabulary_json(
        result.items, directory / job.output.json_name, job=job, document=document
    )
    audit = write_audit_json(
        result.items,
        directory / job.output.audit_name,
        job=job,
        document=document,
        run=result.stats.as_dict(),
    )
    return [tsv, vocabulary, audit]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bookengine",
        description="Verified book-content generation for 4steps workbooks.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    ingest = subcommands.add_parser(
        "ingest", help="Read a book and report its chapter structure."
    )
    ingest.add_argument("--book", required=True, help="Path to the book PDF.")
    ingest.add_argument("--title", help="The book's title, if not the file name.")
    ingest.add_argument(
        "--expected-chapters",
        type=int,
        help="The chapter count from the book's contents page.",
    )
    ingest.add_argument("--cache", default="cache/books", help="Parse cache directory.")
    ingest.add_argument("--no-cache", action="store_true")
    ingest.add_argument(
        "--approve",
        action="store_true",
        help=(
            "Record that you have checked this chapter map against the book, "
            "so `vocab` will run against it."
        ),
    )
    ingest.set_defaults(handler=command_ingest)

    vocab = subcommands.add_parser(
        "vocab", help="Generate a book's vocabulary from a job configuration."
    )
    vocab.add_argument("--config", required=True, help="Path to the job YAML.")
    vocab.add_argument("--book", help="Override the book path in the job.")
    vocab.add_argument("--output", help="Override the output directory.")
    vocab.add_argument("--cache", help="Cache directory (default: <output>/.cache).")
    vocab.add_argument("--no-cache", action="store_true")
    vocab.add_argument(
        "--ingest-only",
        action="store_true",
        help="Validate the book and the lesson plan, then stop.",
    )
    vocab.add_argument("-v", "--verbose", action="store_true")
    vocab.set_defaults(handler=command_vocab)

    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        return arguments.handler(arguments)
    except ConfigError as failure:
        print(f"\n{failure}", file=sys.stderr)
        return EXIT_USAGE
    except BookEngineError as failure:
        print(f"\n{failure}", file=sys.stderr)
        return EXIT_INCOMPLETE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
