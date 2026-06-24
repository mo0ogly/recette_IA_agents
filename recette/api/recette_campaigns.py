"""Read-only catalog over the on-disk recette governance campaigns.

These are a DIFFERENT object from the CRUD campaigns of ``campaign_store`` (the
Lane B run-sequences, ``{id, description, steps}``). A recette campaign
(``campaigns/**/*.campaign.json``) is a governance scenario judged by the
gateway harness: ``{name, objective, teaching, agents[], actions[]}`` where each
action carries an expected verdict (``expect`` = allow|deny|escalate). They are
authored by the recette-campaign-builder skill and scored by ``python -m
recette``; this catalog only exposes them read-only so the console can list and
explain them (it never runs or mutates them).

Source of truth stays the files (I1-friendly: read-only). The catalog reuses
``recette.campaign.load_campaign`` for validation so the API and the CLI agree
on what a valid campaign is -- no parallel parser.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..campaign import CampaignError, load_campaign


def default_campaigns_dir() -> Path:
    """Repo ``campaigns/`` directory (three levels up from this file)."""
    return Path(__file__).resolve().parent.parent.parent / "campaigns"


def _campaign_id(doc: dict, path: Path) -> str:
    """Stable id of a recette campaign: its declared ``name`` (unique by
    convention), falling back to the file stem."""
    name = doc.get("name")
    if isinstance(name, str) and name:
        return name
    return path.stem.replace(".campaign", "")


def _summary(doc: dict, path: Path, root: Path) -> dict:
    rel = path.relative_to(root)
    # Family = first path segment (banque, coverage, role-matrix, rag) or "root".
    family = rel.parts[0] if len(rel.parts) > 1 else "root"
    return {
        "id": _campaign_id(doc, path),
        "family": family,
        "name": doc.get("name", ""),
        "objective": doc.get("objective"),
        "teaching": doc.get("teaching"),
        "action_count": len(doc.get("actions", [])),
        "agent_count": len(doc.get("agents", [])),
        # A macro orchestration campaign declares links to a MAF team; surfaced
        # so the console can badge/group it without fetching the full document.
        "linked": bool(doc.get("links")),
    }


class RecetteCampaignCatalog:
    """Directory-backed, read-only view of ``campaigns/**/*.campaign.json``."""

    def __init__(self, directory: Path | str | None = None) -> None:
        self.directory = Path(directory) if directory is not None else default_campaigns_dir()

    def _files(self) -> list[Path]:
        if not self.directory.exists():
            return []
        return sorted(self.directory.rglob("*.campaign.json"))

    def list(self) -> list[dict]:
        """Summaries of every valid campaign file, sorted by family then id.
        Invalid files are skipped with an ``error`` marker rather than failing
        the whole listing (fail-safe: one bad file never hides the rest)."""
        out: list[dict] = []
        for path in self._files():
            try:
                doc = load_campaign(path)
            except (CampaignError, json.JSONDecodeError) as exc:
                out.append(
                    {
                        "id": path.stem.replace(".campaign", ""),
                        "family": (
                            path.relative_to(self.directory).parts[0]
                            if len(path.relative_to(self.directory).parts) > 1
                            else "root"
                        ),
                        "name": path.name,
                        "objective": None,
                        "teaching": None,
                        "action_count": 0,
                        "agent_count": 0,
                        "error": str(exc),
                    }
                )
                continue
            out.append(_summary(doc, path, self.directory))
        out.sort(key=lambda c: (c["family"], c["id"]))
        return out

    def get(self, campaign_id: str) -> dict | None:
        """Full validated document of one campaign, plus its family, or None."""
        for path in self._files():
            try:
                doc = load_campaign(path)
            except (CampaignError, json.JSONDecodeError):
                continue
            if _campaign_id(doc, path) == campaign_id:
                rel = path.relative_to(self.directory)
                family = rel.parts[0] if len(rel.parts) > 1 else "root"
                return {"family": family, **doc}
        return None
