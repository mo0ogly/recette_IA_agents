"""stringutils -- a tiny pure string helper library. No agent, no GitHub access."""

from __future__ import annotations


def slugify(text: str) -> str:
    out = []
    for ch in text.strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_":
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def truncate(text: str, limit: int) -> str:
    if limit < 0:
        raise ValueError("limit must be non-negative")
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"
