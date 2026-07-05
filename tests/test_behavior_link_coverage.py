"""Hard coverage guard for the behavioral link map.

Four assertions, across BOTH surfaces (corpus/repos and corpus/gitlab):

1. Every subject directory has a link -- an unlinked subject fails.
2. Every link's discovery_subject exists on its declared surface (the dir
   <SURFACE_CORPUS[surface]>/<subject>/repo exists).
3. Every link with an evidence_bundle has a bundle.json that loads as
   EvidenceBundle and whose recording carries the link's agent_id.
4. Every twin's wave yields the quadrant declared in link.expected["quadrant"]
   (via correlate_corpus with runtime_dirty=50).

The deliberately twin-less subjects are frozen below -- the guard fails if
that set grows silently or if one of those subjects unexpectedly gains a twin.
"""

import json
import unittest
from pathlib import Path

from recette.behavior import EvidenceBundle
from recette.behavior.correlate import correlate_corpus
from recette.behavior.links import Link, load_links
from recette.discovery_harness import SURFACE_CORPUS

# Surfaces covered by the link map (and this guard).
_GUARDED_SURFACES = ("github", "gitlab")

# Discovery subjects that are deliberately twin-less (detected=false, no bundle).
# This set MUST NOT grow silently: a new unlinked subject requires updating it here.
# It MUST NOT shrink silently either: removing a subject from corpus without removing
# it here is also a failure.
_NO_TWIN: set[str] = {
    "gh-no-agent",
    "gl-no-agent",
    "gh-shadow-agent",
    "gh-invalid-passport",
    "gh-passport-expired",
    "gh-passport-tampered",
    "gh-passport-scope-overreach",
}


class TestBehaviorLinkCoverage(unittest.TestCase):
    """Coverage guard: every discovery subject is linked and every twin is healthy."""

    # Class-level type declarations so mypy recognises setUpClass assignments.
    links: list[Link]
    linked_subjects: set[str]
    subject_to_link: dict[str | None, Link]
    corpus_subjects: dict[str, set[str]]
    repo_root: Path
    correlation: dict

    # ------------------------------------------------------------------
    # shared fixtures (computed once per test run)
    # ------------------------------------------------------------------

    @classmethod
    def setUpClass(cls) -> None:
        cls.links = load_links()
        cls.linked_subjects = {ln.discovery_subject for ln in cls.links if ln.discovery_subject}
        # Map subject -> link for quick look-up in individual tests.
        cls.subject_to_link = {ln.discovery_subject: ln for ln in cls.links if ln.discovery_subject}
        # Corpus dirs present on disk for each guarded surface.
        cls.corpus_subjects = {}
        for surface in _GUARDED_SURFACES:
            surface_root = SURFACE_CORPUS[surface]
            cls.corpus_subjects[surface] = {
                p.name for p in surface_root.iterdir() if p.is_dir() and not p.name.startswith(".")
            }

        # Resolve repo root once (agent_links paths are repo-relative).
        from recette.behavior.links import DEFAULT_LINKS

        cls.repo_root = DEFAULT_LINKS.parents[1]  # corpus/ -> repo root

        # Run correlate_corpus once for assertion 4 (expensive; reuse).
        cls.correlation = correlate_corpus(cls.links, {"runtime_dirty": 50})

    # ------------------------------------------------------------------
    # Assertion 1: every corpus subject dir has a link
    # ------------------------------------------------------------------

    def test_every_corpus_subject_is_linked(self) -> None:
        """An unlinked discovery subject must be explicitly added to _NO_TWIN."""
        missing: list[str] = []
        for surface in _GUARDED_SURFACES:
            for subject in sorted(self.corpus_subjects[surface]):
                if subject not in self.linked_subjects:
                    missing.append(f"{surface}/{subject}")
        self.assertFalse(
            missing,
            f"Discovery subjects present on disk but absent from agent_links.json: "
            f"{missing}. Either add a link or (for twin-less subjects) add to _NO_TWIN.",
        )

    # ------------------------------------------------------------------
    # Assertion 2: every link's discovery_subject exists on its surface
    # ------------------------------------------------------------------

    def test_every_link_subject_exists_on_surface(self) -> None:
        """The repo tree for each link's discovery_subject must be on disk."""
        missing: list[str] = []
        for ln in self.links:
            if not ln.discovery_subject:
                continue
            surface = ln.surface or "github"
            if surface not in SURFACE_CORPUS:
                missing.append(f"{ln.agent_id}: unknown surface {surface!r}")
                continue
            surface_root = SURFACE_CORPUS[surface]
            repo_tree = surface_root / ln.discovery_subject / "repo"
            if not repo_tree.exists():
                missing.append(
                    f"{ln.agent_id}: {repo_tree} not found "
                    f"(surface={surface!r}, subject={ln.discovery_subject!r})"
                )
        self.assertFalse(
            missing,
            f"Links point to non-existent repo trees: {missing}",
        )

    # ------------------------------------------------------------------
    # Assertion 3: every twin bundle exists, loads, and carries the agent_id
    # ------------------------------------------------------------------

    def test_every_evidence_bundle_is_healthy(self) -> None:
        """bundle.json must exist, parse as EvidenceBundle, and record the agent_id."""
        failures: list[str] = []
        for ln in self.links:
            if not ln.evidence_bundle:
                # No twin expected; covered by the _NO_TWIN guard below.
                continue
            bundle_path = self.repo_root / ln.evidence_bundle / "bundle.json"
            if not bundle_path.exists():
                failures.append(f"{ln.agent_id}: bundle.json missing at {bundle_path}")
                continue
            try:
                data = json.loads(bundle_path.read_text(encoding="utf-8"))
                bundle = EvidenceBundle.from_dict(data)
            except Exception as exc:
                failures.append(f"{ln.agent_id}: bundle.json failed to parse -- {exc}")
                continue
            if ln.agent_id not in bundle.agent_ids():
                failures.append(
                    f"{ln.agent_id}: agent_id not found in bundle "
                    f"(bundle.agent_ids()={bundle.agent_ids()!r})"
                )
        self.assertFalse(
            failures,
            f"Evidence bundle failures: {failures}",
        )

    # ------------------------------------------------------------------
    # Assertion 4: every twin's quadrant matches link.expected["quadrant"]
    # ------------------------------------------------------------------

    def test_every_twin_quadrant_matches_expected(self) -> None:
        """correlate_corpus row quadrant must equal link.expected['quadrant']."""
        # Build a fast lookup: agent_id -> row from the correlation result.
        row_by_agent: dict[str, dict] = {row["agent_id"]: row for row in self.correlation["rows"]}
        failures: list[str] = []
        for ln in self.links:
            expected_quadrant = ln.expected.get("quadrant")
            if expected_quadrant is None:
                # No quadrant expectation (e.g. detected=false links); skip.
                continue
            row = row_by_agent.get(ln.agent_id)
            if row is None:
                failures.append(
                    f"{ln.agent_id}: no correlation row (check unresolved: "
                    f"{self.correlation['unresolved']!r})"
                )
                continue
            actual = row["quadrant"]
            if actual != expected_quadrant:
                failures.append(
                    f"{ln.agent_id}: expected quadrant={expected_quadrant!r} "
                    f"but got {actual!r} "
                    f"(static_flagged={row['static_flagged']}, "
                    f"runtime_dirty={row['runtime_dirty']}, "
                    f"behavioral_score={row['behavioral_score']})"
                )
        self.assertFalse(
            failures,
            f"Quadrant mismatches: {failures}",
        )

    # ------------------------------------------------------------------
    # _NO_TWIN sentinel guard: the set cannot grow or shrink silently
    # ------------------------------------------------------------------

    def test_no_twin_set_is_exact(self) -> None:
        """_NO_TWIN must be exactly the set of twin-less subjects -- no more, no less.

        A new twin-less subject requires an explicit addition to _NO_TWIN.
        A subject that gained a twin must be removed from _NO_TWIN.
        """
        # Twin-less subjects: have a link but evidence_bundle is null.
        actual_no_twin = {
            ln.discovery_subject
            for ln in self.links
            if ln.evidence_bundle is None and ln.discovery_subject
        }
        declared = _NO_TWIN

        extra_in_constant = declared - actual_no_twin
        missing_from_constant = actual_no_twin - declared

        errors: list[str] = []
        if missing_from_constant:
            errors.append(
                f"New twin-less subjects not in _NO_TWIN (add them): "
                f"{sorted(missing_from_constant)}"
            )
        if extra_in_constant:
            errors.append(
                f"Subjects in _NO_TWIN that now have a twin (remove them): "
                f"{sorted(extra_in_constant)}"
            )
        self.assertFalse(errors, "; ".join(errors))


if __name__ == "__main__":
    unittest.main()
