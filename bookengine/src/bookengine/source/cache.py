"""Not parsing the same book twice, and never believing an older parse.

Ingestion is the slow step in a run — a four-hundred-page novel is a minute of
work before a single word has been proposed — and it is also the step whose
answer never changes: the same bytes always produce the same document. That is
what makes it worth caching, and it is why the key is the book's content hash
rather than its path. The same novel renamed is a hit; a different novel saved
over a familiar name is a miss.

What matters more than the speed is what a wrong hit would cost. Everything
downstream treats a `BookDocument` as the truth about the book, so a document
written by an earlier parser — one that split paragraphs differently, or
counted characters differently — would be believed exactly as readily as a
fresh one, and every offset taken from it would be quietly wrong in a way no
later check could catch. Two rules follow, and they are the whole of this
module's design:

    A stored entry carries the format version it was written with, and a
    version this module does not recognise is an empty cache, not old truth.

    An entry becomes visible only once it is complete. Writes go to a temporary
    file and are moved into place, so a run interrupted mid-write leaves either
    the previous entry or nothing at all.

Everything else here is a miss rather than an error. A cache that has been
truncated, hand-edited, or written by a different tool should cost a reparse,
never a crash, because the reparse always produces the right answer.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .document import BookDocument, document_from_dict, document_to_dict

# Bump this whenever a change to ingestion would alter the document produced
# from the same PDF: paragraph assembly, sentence segmentation, chapter
# boundaries, identifier formats, or the serialised shape itself. Entries
# written under any other value are ignored.
CACHE_FORMAT_VERSION = 2

_ENTRY_SUFFIX = ".json"

# Temporary files carry their own suffix so `clear` can tell an abandoned write
# from a finished entry, and so a partial file can never be globbed as one.
_PARTIAL_SUFFIX = ".partial"

# A content hash becomes a file name, so it is checked rather than trusted: a
# value containing a separator would put the entry somewhere other than the
# cache directory. Anything from `pdf.content_hash` passes; nothing else has
# any business being a key.
_HASH = re.compile(r"[0-9a-f]{16,128}")


@dataclass(frozen=True, slots=True)
class ParseCache:
    """A directory of parsed books, keyed by what the book contains.

    `enabled` is a switch rather than an absent cache so that callers can hold
    one object and let configuration decide. A disabled cache never reads and
    never writes, and says so by returning nothing found.
    """

    directory: Path
    enabled: bool = True

    def __post_init__(self) -> None:
        # Configuration and command lines hand over strings. Coercing once here
        # keeps every method below able to assume a real Path.
        object.__setattr__(self, "directory", Path(self.directory))

    def path_for(self, content_hash: str) -> Path:
        """Where the entry for one book lives, whether or not it exists yet."""
        if not _HASH.fullmatch(content_hash):
            raise ValueError(
                f"{content_hash!r} is not a content hash. Cache keys come from "
                "`source.pdf.content_hash` and are lowercase hexadecimal."
            )
        return self.directory / f"{content_hash}{_ENTRY_SUFFIX}"

    def load(self, content_hash: str) -> BookDocument | None:
        """Return the cached document for this book, or nothing.

        Every failure mode collapses to "nothing": a missing file, an
        unreadable one, malformed JSON, a payload from another format version,
        and an entry whose document does not claim the hash it was filed under.
        The last of those catches a copied or renamed cache file, which is the
        one corruption that would otherwise load as a perfectly valid document
        of the wrong book.
        """
        if not self.enabled:
            return None

        path = self.path_for(content_hash)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

        if not isinstance(payload, dict):
            return None
        if payload.get("cache_format_version") != CACHE_FORMAT_VERSION:
            return None

        stored = payload.get("document")
        if not isinstance(stored, dict) or stored.get("content_hash") != content_hash:
            return None

        try:
            return document_from_dict(stored)
        except (KeyError, TypeError, ValueError):
            return None

    def store(self, document: BookDocument) -> Path:
        """Write a parsed document into the cache, atomically.

        The temporary file is created inside the cache directory rather than in
        the system temporary area, because `os.replace` is only atomic within
        one filesystem. Returns the entry's path; on a disabled cache that is
        the path nothing was written to.
        """
        destination = self.path_for(document.content_hash)
        if not self.enabled:
            return destination

        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "cache_format_version": CACHE_FORMAT_VERSION,
            # For a human reading the directory. Nothing depends on it: an
            # entry is valid because of its hash and version, not its age.
            "written_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "document": document_to_dict(document),
        }

        handle, temporary = tempfile.mkstemp(dir=self.directory, suffix=_PARTIAL_SUFFIX)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False)
            os.replace(temporary, destination)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

        return destination

    def clear(self) -> int:
        """Delete every cached document and report how many there were.

        Abandoned temporary files are swept too but not counted, since they
        were never entries. An entry that disappears underneath us is somebody
        else's clear running at the same time, which is the outcome we wanted.
        """
        if not self.directory.is_dir():
            return 0

        removed = 0
        for entry in sorted(self.directory.glob(f"*{_ENTRY_SUFFIX}")):
            try:
                entry.unlink()
            except FileNotFoundError:
                continue
            removed += 1

        for partial in self.directory.glob(f"*{_PARTIAL_SUFFIX}"):
            partial.unlink(missing_ok=True)

        return removed
