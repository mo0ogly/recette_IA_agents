"""Eurodated run registry -- pure filesystem ops, no clock/random (I4).

Every run is stored under:
  <root>/<category>/<eurodate>_<group_id>/<run_id>/

The registry never calls the clock.  Callers pass ``eurodate`` strings
(e.g. "2026-06-25T14-30-00") so all operations remain deterministic.

Deletion archives to <root>/_archive/<run_id>.tar.gz then purges the live
dir.  This is work-memory (R25, docs/tracking/runs/ is gitignored), never
the committed audit-plane event store, so local purge is allowed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger(__name__)

# Default root resolved from env (R5 -- no hardcoded absolute path).
_DEFAULT_ROOT_RELATIVE = Path("docs") / "tracking" / "runs"


def _registry_root() -> Path:
    """Resolve the registry root from env or fall back to the repo default."""
    env_val = os.environ.get("INSPECT_IA_AGENTS_RUNS_ROOT", "")
    if env_val:
        return Path(env_val)
    # Walk up from this file to the repo root (recette/runs/registry.py -> repo/).
    return Path(__file__).resolve().parent.parent.parent / _DEFAULT_ROOT_RELATIVE


# ---------------------------------------------------------------------------
# Public ref types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GroupRef:
    """Opaque handle returned by new_group()."""

    path: Path
    category: str
    group_id: str


@dataclass(frozen=True)
class RunRef:
    """Opaque handle returned by new_run()."""

    path: Path
    run_id: str
    group: GroupRef


# ---------------------------------------------------------------------------
# SHA-256 helpers (pattern from scripts/export_anssi_bundle.py:48,71)
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    """Return the hex SHA-256 digest of the file at *path*."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _chain(entries: list[dict]) -> str:
    """Tamper-evident root: fold each file digest into a running hash (I1 style).

    Entries are sorted by ``file`` key so the result is independent of
    insertion order (I4).
    """
    root = "0" * 64
    for e in sorted(entries, key=lambda x: x["file"]):
        root = hashlib.sha256(f"{root}{e['sha256']}".encode()).hexdigest()
    return root


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class RunRegistry:
    """Filesystem registry for eurodated run artefacts.

    All mutating operations never call the system clock; callers supply the
    ``eurodate`` parameter (I4).

    The root defaults to ``INSPECT_IA_AGENTS_RUNS_ROOT`` env or
    ``docs/tracking/runs/`` relative to the repo (R5).
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root: Path = root if root is not None else _registry_root()

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def new_group(
        self,
        *,
        category: str,
        group_id: str,
        eurodate: str,
        label: str,
    ) -> GroupRef:
        """Create a group dir and write ``_group.json``.

        Returns a :class:`GroupRef` for subsequent ``new_run`` calls.
        """
        group_dir = self._root / category / f"{eurodate}_{group_id}"
        group_dir.mkdir(parents=True, exist_ok=True)
        meta_path = group_dir / "_group.json"
        meta: dict = {
            "category": category,
            "group_id": group_id,
            "eurodate": eurodate,
            "label": label,
            "status": "open",
            "runs": [],
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return GroupRef(path=group_dir, category=category, group_id=group_id)

    def new_run(
        self,
        *,
        group: GroupRef,
        run_id: str,
        kind: str,
        eurodate: str,
        replay_of: str | None = None,
    ) -> RunRef:
        """Create a run dir under *group*, write ``meta.json`` and ``annotations.json``.

        Appends *run_id* to the group's ``_group.json.runs`` list.
        Returns a :class:`RunRef`.
        """
        run_dir = group.path / run_id
        artifacts_dir = run_dir / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        meta: dict = {
            "id": run_id,
            "kind": kind,
            "eurodate": eurodate,
            "parent_group": group.group_id,
            "status": "running",
            "artifacts": [],
            "root_hash": None,
            "replay_of": replay_of,
        }
        (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        annotations: dict = {
            "tags": [],
            "comment": "",
            "label": "",
            "retention": "keep",
        }
        (run_dir / "annotations.json").write_text(
            json.dumps(annotations, indent=2), encoding="utf-8"
        )

        # Append this run's id to the group manifest.
        group_meta_path = group.path / "_group.json"
        group_meta: dict = json.loads(group_meta_path.read_text(encoding="utf-8"))
        if run_id not in group_meta["runs"]:
            group_meta["runs"].append(run_id)
        group_meta_path.write_text(json.dumps(group_meta, indent=2), encoding="utf-8")

        return RunRef(path=run_dir, run_id=run_id, group=group)

    def write_artifact(self, run: RunRef, name: str, content: str | bytes) -> None:
        """Write *content* to ``<run>/artifacts/<name>``.

        Rejects names containing ``/`` or ``..`` to prevent path traversal.
        """
        if "/" in name or ".." in name:
            raise ValueError(f"invalid artifact name {name!r}: must not contain '/' or '..'")
        artifacts_dir = run.path / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        dest = artifacts_dir / name
        if isinstance(content, str):
            dest.write_text(content, encoding="utf-8")
        else:
            dest.write_bytes(content)

    def seal(self, run: RunRef) -> dict:
        """Compute per-file sha256 + chained root_hash; write final meta.

        Returns the updated meta dict.  Never reads the clock (I4).
        """
        artifacts_dir = run.path / "artifacts"
        entries: list[dict] = []
        if artifacts_dir.exists():
            for f in sorted(artifacts_dir.iterdir()):
                if f.is_file():
                    entries.append({"file": f.name, "sha256": _sha256(f)})

        root_hash = _chain(entries)

        meta_path = run.path / "meta.json"
        meta: dict = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["status"] = "sealed"
        meta["artifacts"] = entries
        meta["root_hash"] = root_hash
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def tree(self) -> dict:
        """Return a category > group > run tree by walking the registry root.

        Groups are sorted by eurodate descending within each category.
        """
        categories: list[dict] = []
        if not self._root.exists():
            return {"categories": categories}

        for cat_dir in sorted(self._root.iterdir()):
            # Reserved dirs are not categories: "_archive" (delete target) and
            # "latest" (the back-compat symlink dir).
            if not cat_dir.is_dir() or cat_dir.name.startswith("_") or cat_dir.name == "latest":
                continue
            groups: list[dict] = []
            for g_dir in sorted(cat_dir.iterdir(), reverse=True):
                if not g_dir.is_dir() or g_dir.name.startswith("_"):
                    continue
                gm_path = g_dir / "_group.json"
                if not gm_path.exists():
                    continue
                try:
                    gm: dict = json.loads(gm_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    _log.warning("failed to read group meta %s: %s", gm_path, exc)
                    continue
                runs: list[dict] = []
                for run_id in gm.get("runs", []):
                    meta_path = g_dir / run_id / "meta.json"
                    if meta_path.exists():
                        try:
                            rm: dict = json.loads(meta_path.read_text(encoding="utf-8"))
                            runs.append(
                                {
                                    "id": rm.get("id", run_id),
                                    "kind": rm.get("kind", ""),
                                    "eurodate": rm.get("eurodate", ""),
                                    "status": rm.get("status", "unknown"),
                                }
                            )
                        except (OSError, json.JSONDecodeError) as exc:
                            _log.warning("failed to read run meta %s: %s", meta_path, exc)
                groups.append(
                    {
                        "group_id": gm.get("group_id", g_dir.name),
                        "eurodate": gm.get("eurodate", ""),
                        "label": gm.get("label", ""),
                        "status": gm.get("status", "unknown"),
                        "runs": runs,
                    }
                )
            categories.append({"category": cat_dir.name, "groups": groups})
        return {"categories": categories}

    def find_run(self, run_id: str) -> RunRef | None:
        """Search the registry tree for a run by its id.  Returns None if not found."""
        if not self._root.exists():
            return None
        for cat_dir in self._root.iterdir():
            if not cat_dir.is_dir() or cat_dir.name.startswith("_"):
                continue
            for g_dir in cat_dir.iterdir():
                if not g_dir.is_dir() or g_dir.name.startswith("_"):
                    continue
                run_dir = g_dir / run_id
                if (run_dir / "meta.json").exists():
                    # Reconstruct a minimal GroupRef.
                    gm_path = g_dir / "_group.json"
                    if gm_path.exists():
                        try:
                            gm: dict = json.loads(gm_path.read_text(encoding="utf-8"))
                            group = GroupRef(
                                path=g_dir,
                                category=gm.get("category", cat_dir.name),
                                group_id=gm.get("group_id", g_dir.name),
                            )
                        except (OSError, json.JSONDecodeError):
                            group = GroupRef(
                                path=g_dir,
                                category=cat_dir.name,
                                group_id=g_dir.name,
                            )
                    else:
                        group = GroupRef(path=g_dir, category=cat_dir.name, group_id=g_dir.name)
                    return RunRef(path=run_dir, run_id=run_id, group=group)
        return None

    def read_run(self, run_id: str) -> dict:
        """Return ``{meta, annotations, artifacts}`` for *run_id*.

        Raises ``KeyError`` if the run is not found.
        """
        ref = self.find_run(run_id)
        if ref is None:
            raise KeyError(f"run {run_id!r} not found")
        meta: dict = json.loads((ref.path / "meta.json").read_text(encoding="utf-8"))
        ann: dict = json.loads((ref.path / "annotations.json").read_text(encoding="utf-8"))
        artifacts_dir = ref.path / "artifacts"
        artifact_names: list[str] = []
        if artifacts_dir.exists():
            artifact_names = sorted(f.name for f in artifacts_dir.iterdir() if f.is_file())
        return {"meta": meta, "annotations": ann, "artifacts": artifact_names}

    def read_artifact(self, run: RunRef, name: str) -> str:
        """Return the text content of artifact *name* in *run*.

        Raises ``ValueError`` if *name* escapes the run's artifacts directory
        (path-traversal guard).
        """
        artifacts_dir = (run.path / "artifacts").resolve()
        candidate = (artifacts_dir / name).resolve()
        # Ensure the resolved path is strictly under the artifacts dir.
        try:
            candidate.relative_to(artifacts_dir)
        except ValueError as exc:
            raise ValueError(f"artifact name {name!r} escapes the run artifacts directory") from exc
        if not candidate.exists():
            raise FileNotFoundError(f"artifact {name!r} not found in run {run.run_id!r}")
        return candidate.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Update / Delete / Replay
    # ------------------------------------------------------------------

    def annotate(
        self,
        run_id: str,
        *,
        tags: list[str] | None = None,
        comment: str | None = None,
        label: str | None = None,
        retention: str | None = None,
    ) -> dict:
        """Mutate only ``annotations.json`` for *run_id*.

        meta.json and artifacts are never touched (I1-style separation).
        Returns the updated annotations dict.
        """
        ref = self.find_run(run_id)
        if ref is None:
            raise KeyError(f"run {run_id!r} not found")
        ann_path = ref.path / "annotations.json"
        ann: dict = json.loads(ann_path.read_text(encoding="utf-8"))
        if tags is not None:
            ann["tags"] = tags
        if comment is not None:
            ann["comment"] = comment
        if label is not None:
            ann["label"] = label
        if retention is not None:
            ann["retention"] = retention
        ann_path.write_text(json.dumps(ann, indent=2), encoding="utf-8")
        return ann

    def delete(self, run_id: str) -> Path:
        """Archive the run dir into ``<root>/_archive/<run_id>.tar.gz`` then purge it.

        Returns the archive path.  Raises ``KeyError`` if run not found.
        This only touches work-memory (R25) -- never the audit-plane store.
        """
        ref = self.find_run(run_id)
        if ref is None:
            raise KeyError(f"run {run_id!r} not found")

        archive_dir = self._root / "_archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"{run_id}.tar.gz"

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(ref.path, arcname=run_id)

        shutil.rmtree(ref.path)
        _log.info("run %s archived to %s and purged", run_id, archive_path)
        return archive_path

    def spawn_replay(
        self,
        parent_id: str,
        *,
        eurodate: str,
        run_id: str | None = None,
    ) -> RunRef:
        """Create a child run linked to *parent_id* via ``meta.replay_of``.

        The parent run is never mutated (I1-style).  The child is created as a
        sibling run under the parent's group with ``replay_of=parent_id``.
        Returns the new RunRef (child is in ``running`` state; caller seals it).
        """
        parent = self.find_run(parent_id)
        if parent is None:
            raise KeyError(f"parent run {parent_id!r} not found")

        # Determine parent's kind from its meta.
        parent_meta: dict = json.loads((parent.path / "meta.json").read_text(encoding="utf-8"))
        kind = parent_meta.get("kind", "replay")

        child_id = run_id or f"{parent_id}-replay-{eurodate}"

        return self.new_run(
            group=parent.group,
            run_id=child_id,
            kind=kind,
            eurodate=eurodate,
            replay_of=parent_id,
        )
