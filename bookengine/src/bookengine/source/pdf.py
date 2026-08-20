"""Getting text out of a PDF, with enough geometry to rebuild the page.

This layer knows nothing about chapters, lessons, or vocabulary. It answers one
question: what characters are on each page, in what order, and where. Every
later decision — what a paragraph is, where a chapter starts, which sentence a
quotation came from — is made from these lines, so nothing here is allowed to
be clever. Repairs that change characters happen further up, in `layout`, and
are counted there.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from ..errors import UnsupportedBookError

# A page carrying fewer than this many characters is an illustration, a part
# title, or a scan. One such page is normal; a book of them is not.
SPARSE_PAGE_CHARACTERS = 120

# If this share of pages is sparse, the book is not text-based enough to verify
# quotations against, and V1 refuses it rather than guessing at OCR.
MAX_SPARSE_PAGE_SHARE = 0.35

# Two spans on one line are different words when the gap between them is a
# meaningful fraction of the type size. Below it they are one word split by a
# font change, which is common in italicised dialogue.
_SPAN_GAP_RATIO = 0.18


@dataclass(frozen=True, slots=True)
class TextLine:
    """One horizontal run of text, as the PDF laid it out.

    `furniture` is set by `layout.detect_furniture` rather than here — this
    module has no opinion about what a line is for. It travels on the line so
    that one stream can serve two purposes: chapter detection reads every line,
    including the running heads that some books set their headings beside, and
    paragraph assembly reads only the ones that are prose.
    """

    page: int
    block: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    furniture: bool = False

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass(slots=True)
class PageText:
    """Every line on one page, in reading order."""

    number: int
    width: float
    height: float
    lines: list[TextLine] = field(default_factory=list)

    @property
    def character_count(self) -> int:
        return sum(len(line.text) for line in self.lines)


@dataclass(slots=True)
class ExtractedBook:
    """A whole PDF, reduced to positioned lines of text."""

    path: Path
    content_hash: str
    page_count: int
    pages: list[PageText]
    sparse_pages: list[int]

    def line_count(self) -> int:
        return sum(len(page.lines) for page in self.pages)

    def character_count(self) -> int:
        return sum(page.character_count for page in self.pages)


def content_hash(path: Path) -> str:
    """Hash the file itself, so a cache entry belongs to exactly one book.

    The path is not part of it: the same book renamed is the same book, and a
    different book at a familiar path is not.
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _join_spans(spans: list[dict]) -> tuple[str, float]:
    """Concatenate one line's spans, restoring spaces the PDF only implied.

    A PDF splits a line at every font change, and whether a space survives that
    split depends on the generator. Where the gap between two spans is wide
    enough to be a real space, one is inserted; where it is not, the spans are
    joined tight so an italicised word is not broken in half.
    """
    parts: list[str] = []
    sizes: list[float] = []
    previous_x1: float | None = None

    for span in spans:
        text = span.get("text", "")
        if not text:
            continue

        size = float(span.get("size", 0.0))
        sizes.append(size)
        x0, _, x1, _ = span["bbox"]

        if (
            parts
            and previous_x1 is not None
            and not parts[-1].endswith(" ")
            and not text.startswith(" ")
            and x0 - previous_x1 > max(size, 1.0) * _SPAN_GAP_RATIO
        ):
            parts.append(" ")

        parts.append(text)
        previous_x1 = float(x1)

    return "".join(parts), max(sizes, default=0.0)


def extract_pdf(path: Path | str) -> ExtractedBook:
    """Read a PDF into positioned lines, or refuse it.

    Refusal is the point of the sparse-page check. An image-only scan extracts
    as a handful of stray characters, and every quotation "verified" against
    that would be verified against nothing.
    """
    path = Path(path)
    if not path.is_file():
        raise UnsupportedBookError(f"No such book file: {path}")

    try:
        document = pymupdf.open(path)
    except Exception as cause:  # pragma: no cover - depends on the file
        raise UnsupportedBookError(f"Could not open {path.name}: {cause}") from cause

    with document:
        if document.is_encrypted and not document.authenticate(""):
            raise UnsupportedBookError(
                f"{path.name} is password-protected. Supply a decrypted copy."
            )

        pages: list[PageText] = []
        sparse: list[int] = []

        for index, page in enumerate(document, start=1):
            rectangle = page.rect
            extracted = PageText(
                number=index, width=rectangle.width, height=rectangle.height
            )
            content = page.get_text("dict", sort=True)

            for block_index, block in enumerate(content.get("blocks", [])):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    text, size = _join_spans(line.get("spans", []))
                    if not text.strip():
                        continue
                    x0, y0, x1, y1 = line["bbox"]
                    extracted.lines.append(
                        TextLine(
                            page=index,
                            block=block_index,
                            text=text.strip(),
                            x0=float(x0),
                            y0=float(y0),
                            x1=float(x1),
                            y1=float(y1),
                            size=size,
                        )
                    )

            if extracted.character_count < SPARSE_PAGE_CHARACTERS:
                sparse.append(index)
            pages.append(extracted)

    if not pages:
        raise UnsupportedBookError(f"{path.name} has no pages.")

    sparse_share = len(sparse) / len(pages)
    if sparse_share > MAX_SPARSE_PAGE_SHARE:
        raise UnsupportedBookError(
            f"{path.name} does not extract as text: {len(sparse)} of {len(pages)} "
            f"pages carry almost no characters ({sparse_share:.0%}, limit "
            f"{MAX_SPARSE_PAGE_SHARE:.0%}). This is normally an image-only scan. "
            "OCR is not supported in this version; supply a text-based PDF."
        )

    return ExtractedBook(
        path=path,
        content_hash=content_hash(path),
        page_count=len(pages),
        pages=pages,
        sparse_pages=sparse,
    )
