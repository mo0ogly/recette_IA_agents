"""Product CMS lab entity: content items (derived from id)."""

from __future__ import annotations

from dataclasses import dataclass

from ._common import _edigest, _int, _pick

__all__ = [
    "CONTENT_STATES",
    "SEED_ARCHIVED_CONTENT",
    "SEED_CONTENT",
    "Content",
    "derive_content",
]

CONTENT_STATES = ("draft", "in_review", "published")
SEED_CONTENT = ("cms/content/home", "cms/content/pricing", "cms/content/blog")
SEED_ARCHIVED_CONTENT = ("cms/content/archived-1",)


@dataclass(frozen=True)
class Content:
    """A CMS content item, fully derived from its id."""

    content_id: str
    state: str
    version: str
    word_count: int

    @property
    def archived(self) -> bool:
        """Archived content is read-only; edit/publish/delete is rejected."""
        return self.state == "archived"

    def summary(self) -> dict:
        return {"content_id": self.content_id, "state": self.state, "version": self.version}


def derive_content(content_id: str) -> Content:
    cid = content_id or "cms/content/unknown"
    dig = _edigest("content", cid)
    state = "archived" if cid in SEED_ARCHIVED_CONTENT else _pick(dig, CONTENT_STATES)
    return Content(
        content_id=cid,
        state=state,
        version=f"v{_int(dig, 1, 50)}",
        word_count=_int(dig, 10, 5000, offset=8),
    )
