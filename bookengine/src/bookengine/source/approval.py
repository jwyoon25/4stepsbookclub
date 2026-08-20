"""A person's word that a chapter map is right, remembered per book.

Chapter assignment is the one fact in a workbook that nothing downstream can
check. Every quotation can be real, every word can occur where it says, and the
whole book can still be filed one chapter off — so where ingestion is unsure,
the right answer is to ask someone who has the book open.

Asking once is the point of this module. The same PDF parsed the same way
produces the same chapter map, so an approval is worth keeping; a reviewer who
has checked that chapter 31 really is thirty-seven characters long should not be
asked again tomorrow.

What is approved is the map, not the file. The record carries a fingerprint of
the chapters — their numbers, headings, pages and lengths — so a change to the
parser invalidates every approval it would have altered, without anyone having
to remember to clear anything. A file hash alone would let a new parser inherit
the confidence earned by the old one's output, which is the one way this could
be actively harmful.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .document import BookDocument

APPROVALS_FILE = "approvals.json"

# Bumped when the record's shape changes. An unrecognised file is no approvals,
# never a partially-understood one.
APPROVAL_FORMAT_VERSION = 1


def chapter_fingerprint(document: BookDocument) -> str:
    """A short digest of the chapter map a reviewer would have been looking at.

    Everything a person checks in the ingestion report is in here: which
    chapters exist, what their headings say, which pages they cover, and how
    long they are. Anything that would change one of those lines changes the
    fingerprint, and the approval stops applying.
    """
    digest = hashlib.sha256()
    for chapter in document.chapters:
        digest.update(
            f"{chapter.number}\x1f{chapter.heading}\x1f{chapter.page_start}"
            f"\x1f{chapter.page_end}\x1f{len(chapter.text)}\x1e".encode()
        )
    return digest.hexdigest()[:32]


@dataclass(frozen=True, slots=True)
class Approval:
    """One reviewed chapter map."""

    content_hash: str
    fingerprint: str
    chapters: int
    title: str
    approved_at: str
    reviewed: list[str]

    def covers(self, document: BookDocument) -> bool:
        return (
            self.content_hash == document.content_hash
            and self.fingerprint == chapter_fingerprint(document)
        )

    def as_dict(self) -> dict:
        return {
            "content_hash": self.content_hash,
            "fingerprint": self.fingerprint,
            "chapters": self.chapters,
            "title": self.title,
            "approved_at": self.approved_at,
            "reviewed": list(self.reviewed),
        }


@dataclass(frozen=True, slots=True)
class ApprovalStore:
    """The approvals recorded on this machine, in one small file.

    Deliberately a plain file next to the parse cache rather than anything with
    a schema or a server. It holds one line per book somebody has looked at, it
    is readable by the person who wrote it, and losing it costs one repeated
    review rather than a wrong workbook.
    """

    directory: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "directory", Path(self.directory))

    @property
    def path(self) -> Path:
        return self.directory / APPROVALS_FILE

    def _load(self) -> dict[str, dict]:
        """Every recorded approval, or none. A damaged file is no approvals.

        Failing open here would be the wrong direction: an unreadable file
        should cost a review, not grant one.
        """
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if (
            not isinstance(payload, dict)
            or payload.get("approval_format_version") != APPROVAL_FORMAT_VERSION
        ):
            return {}
        entries = payload.get("approvals")
        return entries if isinstance(entries, dict) else {}

    def find(self, document: BookDocument) -> Approval | None:
        """The approval covering this exact chapter map, if somebody gave one."""
        entry = self._load().get(document.content_hash)
        if not isinstance(entry, dict):
            return None
        try:
            approval = Approval(
                content_hash=entry["content_hash"],
                fingerprint=entry["fingerprint"],
                chapters=entry["chapters"],
                title=entry["title"],
                approved_at=entry["approved_at"],
                reviewed=list(entry.get("reviewed", [])),
            )
        except (KeyError, TypeError):
            return None
        return approval if approval.covers(document) else None

    def record(self, document: BookDocument, reviewed: list[str]) -> Approval:
        """Write down that a person accepted this chapter map, and what of it.

        `reviewed` is the list of concerns the report raised at the time. It is
        stored so that a later reader can see what was actually signed off,
        rather than an unqualified "approved" that might have been given
        against a much shorter list.
        """
        approval = Approval(
            content_hash=document.content_hash,
            fingerprint=chapter_fingerprint(document),
            chapters=len(document.chapters),
            title=document.title,
            approved_at=datetime.now(UTC).isoformat(timespec="seconds"),
            reviewed=list(reviewed),
        )

        approvals = self._load()
        approvals[document.content_hash] = approval.as_dict()
        self._write(approvals)
        return approval

    def forget(self, content_hash: str) -> bool:
        approvals = self._load()
        if approvals.pop(content_hash, None) is None:
            return False
        self._write(approvals)
        return True

    def _write(self, approvals: dict[str, dict]) -> None:
        """Replace the file atomically, so an interrupted write loses nothing."""
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "approval_format_version": APPROVAL_FORMAT_VERSION,
            "approvals": approvals,
        }
        handle, temporary = tempfile.mkstemp(dir=self.directory, suffix=".partial")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
            os.replace(temporary, self.path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
