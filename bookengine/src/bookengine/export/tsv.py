"""The run in the one shape a tutor can use: a block to paste into the Sheet.

Everything upstream of this module is about being right. This module is about
arriving. A tutor opens the Vocabulary tab, clicks A5, and pastes once, so the
output has to be tab-separated text whose columns line up with the tab's
headings and whose rows the builder will accept.

Two things could quietly ruin that. A quotation containing a newline would end
its row early and shift every column after it, which is why every cell is
flattened. And a definition three characters over the schema's limit would be
accepted here and rejected at import, which is why the limits are checked here
instead — a run that produced an unusable row must fail on the operator's
machine, not on the tutor's.

Filtering to `READY` is repeated here on purpose. The pipeline already only
hands over finished items; this is the last gate, and it is the one that decides
what a reader of the file sees, so it does not delegate.
"""

from __future__ import annotations

from pathlib import Path

from ..errors import VerificationError
from ..source.text import flatten_for_cell
from ..vocabulary.models import WORKBOOK_STATUS, Status, VocabularyItem
from .workbook_contract import (
    VOCABULARY_COLUMN_FIELDS,
    VOCABULARY_COLUMNS,
    VOCABULARY_FIELD_LIMITS,
    VOCABULARY_REQUIRED_FIELDS,
)


def exportable_items(items: list[VocabularyItem]) -> list[VocabularyItem]:
    """The items that may be written out, in the order they will appear.

    Ordering by lesson and then by order is what makes two runs of the same job
    comparable line by line, and it is the order the workbook prints in anyway.
    """
    ready = [item for item in items if item.status is Status.READY]
    return sorted(
        ready,
        key=lambda item: (
            item.lesson,
            item.order is None,
            item.order or 0,
            item.normalized_term,
        ),
    )


def vocabulary_rows(items: list[VocabularyItem]) -> list[list[str]]:
    """Every ready item as a row of cells, checked against the Sheet's contract.

    The checks here all describe rows the workbook builder would refuse. Raising
    is the point: an engine that writes a file the builder rejects has not
    failed loudly, it has failed silently and handed the failure to someone
    else.
    """
    rows: list[list[str]] = []
    placed: dict[tuple[int, int], str] = {}

    for item in exportable_items(items):
        if item.order is None:
            raise VerificationError(
                f"Lesson {item.lesson}: {item.term!r} is ready but has no order, "
                "and the Vocabulary tab requires a whole number in the Order "
                "column of every row."
            )

        position = (item.lesson, item.order)
        if position in placed:
            raise VerificationError(
                f"Lesson {item.lesson} has two items at order {item.order}: "
                f"{placed[position]!r} and {item.term!r}. The workbook builder "
                "refuses a repeated order within a lesson."
            )
        placed[position] = item.term

        # Every cell is flattened, including the ones that could never hold a
        # tab, so the rule stays "no cell may shift a column" rather than a list
        # of exceptions. This cannot invalidate the excerpt: `verify_excerpt`
        # compares `flatten_for_cell(raw)` with the exported string, and
        # `normalize_for_matching` collapses whitespace on both sides, so the
        # flattened excerpt and the book's own text are the same text in the
        # only form either check reads them in.
        row = [flatten_for_cell(value) for value in _cells(item)]
        _check_against_contract(item, row)
        rows.append(row)

    return rows


def render_tsv(items: list[VocabularyItem], *, include_header: bool = True) -> str:
    """The rows as tab-separated text, ready for the clipboard or a file."""
    lines: list[list[str]] = [list(VOCABULARY_COLUMNS)] if include_header else []
    lines.extend(vocabulary_rows(items))
    # Each line ends in a newline, the last one included. A trailing blank line
    # costs nothing on paste: `dataRows` in sheet-contract.mjs skips any row
    # with no content in it.
    return "".join("\t".join(line) + "\n" for line in lines)


def write_tsv(
    items: list[VocabularyItem], path: Path, *, include_header: bool = True
) -> Path:
    """Write the paste block to disk, preserving every character in it.

    Korean meanings, the book's curly quotes and its em dashes are the content,
    not decoration, so the file is UTF-8 with no byte-order mark — a mark would
    be read as part of the first cell — and `newline=""` keeps the line endings
    exactly the ones `render_tsv` wrote on every platform.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(render_tsv(items, include_header=include_header))
    return path


def _cells(item: VocabularyItem) -> list[str]:
    """One item's cells in column order, before flattening."""
    return [
        # The Sheet's Status column is a note to the people working on the book,
        # so it carries the engine's word for a proved row rather than the
        # internal status name.
        WORKBOOK_STATUS,
        str(item.lesson),
        str(item.order),
        item.term,
        item.korean_meaning or "",
        item.definition or "",
        item.excerpt or "",
        item.excerpt_context or "",
        # Derived from the locator by `ExcerptLocator.chapter_reference`. No
        # model's claim about which chapter a passage came from reaches this
        # column, or any other.
        item.chapter_reference or "",
    ]


def _check_against_contract(item: VocabularyItem, row: list[str]) -> None:
    """Refuse a row the workbook builder would refuse."""
    if len(row) != len(VOCABULARY_COLUMNS):
        raise VerificationError(
            f"Lesson {item.lesson} item {item.order} ({item.term!r}) produced "
            f"{len(row)} cells for {len(VOCABULARY_COLUMNS)} columns."
        )

    for column, cell in zip(VOCABULARY_COLUMNS, row, strict=True):
        field = VOCABULARY_COLUMN_FIELDS[column]
        if field is None:
            continue

        if field in VOCABULARY_REQUIRED_FIELDS and not cell.strip():
            raise VerificationError(
                f"Lesson {item.lesson} item {item.order} ({item.term!r}) has "
                f"nothing in {field}, and the workbook requires that column "
                f'("{column}") in every vocabulary row.'
            )

        limit = VOCABULARY_FIELD_LIMITS[field]
        if len(cell) > limit:
            raise VerificationError(
                f"Lesson {item.lesson} item {item.order} ({item.term!r}): "
                f"{field} is {len(cell)} characters, over the workbook limit of "
                f"{limit}. The workbook builder would reject this row, so the "
                "run is not finished."
            )
