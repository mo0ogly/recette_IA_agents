"""Close the corpus loop: promote a CAUGHT anomaly into a negative subject.

A red-team sim scenario whose re-judged verdict is ``incorrect`` is a true
positive -- the recette caught the agent. ``promote_scenario`` freezes that
caught anomaly into a durable negative corpus subject under
``<out_root>/incorrect/<slug>/`` so the identification recette can score it like
any other hand-authored negative. One shared function powers the CLI command
(``recette redteam-promote``) and the POST API endpoint
(``/sim/scenarios/{id}/promote``).

Family-aware over the unified agent model. The scenario family is read from the
file suffix and the embedded target's ``kind``:

- a MAF scenario (``*.scenario.json``, ``target_spec.kind == maf_agent``) is
  replayed with ``recette.redteam_recette`` and frozen with the MAF subject
  layout (``spec.json`` + ``actions.json``), matching ``corpus/maf_agents/``.
- a git scenario (``*.git-scenario.json``, ``target_manifest.kind == git_agent``)
  is replayed with ``recette.redteam_git`` and frozen with the git subject layout
  (``manifest.json`` + ``scenario.json``), matching ``corpus/agents/``.

The three documents come straight from ``redteam.to_corpus_subject`` (each
schema-valid, ground-truth derived from the judge so it never drifts, I4). The
decision path is deterministic (no clock, no random); only the final file writes
are side effects. Existing subject files are never clobbered unless ``overwrite``
is set (I1 immutability).
"""

from __future__ import annotations

import json
from pathlib import Path

from .redteam import to_corpus_subject
from .redteam_git import _judge_once, _validate
from .redteam_recette import _replay

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SIM_DIR = _REPO_ROOT / "corpus" / "sim"


class UnknownScenarioError(ValueError):
    """Raised when no sim scenario matches the requested id. A ValueError subclass
    so existing ``except ValueError`` callers keep working; the endpoint catches it
    specifically to map an unknown id to 404 (vs 422 for a malformed/true-negative
    scenario) without stringly-typed message matching."""


# Per-family on-disk layout for the frozen subject. The actions doc returned by
# to_corpus_subject is written under the family's actions filename; the manifest
# under the family's manifest filename. These MATCH the real corpus layout:
# git -> corpus/agents/incorrect/<slug>/{manifest.json,scenario.json}
# maf -> corpus/maf_agents/incorrect/<slug>/{spec.json,actions.json}
_MANIFEST_FILENAME = {"git_agent": "manifest.json", "maf_agent": "spec.json"}
_ACTIONS_FILENAME = {"git_agent": "scenario.json", "maf_agent": "actions.json"}

# Per-family default corpus root. A frozen subject MUST land in the tree its
# family's corpus lives in, so that `recette validate` sees it: git subjects in
# corpus/agents/, MAF subjects in corpus/maf_agents/. An explicit caller-supplied
# out_root (e.g. a test tmp dir) always wins over this default.
_DEFAULT_OUT_ROOT = {"git_agent": "corpus/agents", "maf_agent": "corpus/maf_agents"}


def _default_out_root(family: str) -> str:
    """The corpus root a family's frozen subject must be written under when the
    caller does not pin one. Raises ValueError on an unknown family (fail-safe)."""
    try:
        return _DEFAULT_OUT_ROOT[family]
    except KeyError as exc:
        raise ValueError(f"unknown subject family {family!r}") from exc


def _load_scenario(scenario_id: str) -> tuple[dict, str]:
    """Locate a scenario by id across MAF (*.scenario.json) and git
    (*.git-scenario.json) files. Returns ``(scenario_dict, family)`` where family
    is ``"maf_agent"`` or ``"git_agent"``. Raises ValueError on an unknown id.

    Git files end in ``-scenario.json`` (not ``.scenario.json``), so the two
    globs are disjoint; we scan MAF first then git, matching on the embedded
    ``scenario_id`` (not the filename) so the on-disk name is never load-bearing.
    """
    for path in sorted(_SIM_DIR.glob("*.scenario.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("scenario_id") == scenario_id:
            return data, "maf_agent"
    for path in sorted(_SIM_DIR.glob("*.git-scenario.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("scenario_id") == scenario_id:
            return data, "git_agent"
    raise UnknownScenarioError(f"unknown scenario id {scenario_id!r}")


def _run_typed(scenario: dict, family: str) -> tuple[dict, list, str | None]:
    """Replay a scenario with its typed runner and return ``(manifest,
    action_log, verdict)``. The action_log is the TYPED log (MafAction /
    AgentAction) that ``to_corpus_subject`` expects -- the *_view functions only
    return dicts, so we drive the typed runners directly.
    """
    if family == "maf_agent":
        spec, result, verdict = _replay(scenario)
        return spec, result.action_log, verdict.verdict
    manifest = _validate(scenario)
    result, verdict = _judge_once(scenario, manifest)
    return manifest, result.actions, verdict.verdict


def promote_scenario(
    scenario_id: str,
    *,
    out_root: str | None = None,
    overwrite: bool = False,
) -> dict:
    """Freeze a caught red-team anomaly into a negative corpus subject.

    Locates the scenario by id (MAF or git), replays it with the typed runner to
    recover the manifest/spec, the typed action log and the verdict, then derives
    the violation_type and freezes the run via ``to_corpus_subject``. The three
    documents are written under ``<out_root>/incorrect/<slug>/`` with the
    family's filenames (git: manifest/scenario; MAF: spec/actions), plus the
    shared ``ground-truth.json``.

    ``out_root`` is family-aware: when omitted (None) it defaults to the family's
    corpus root (git -> ``corpus/agents``, MAF -> ``corpus/maf_agents``) so the
    frozen subject lands where ``recette validate`` looks for it. An explicit
    caller-supplied ``out_root`` (e.g. a test tmp dir) is honored verbatim.

    Returns ``{"slug", "created", "verdict", "violation_type"}``.

    Raises:
        UnknownScenarioError -- no scenario matches ``scenario_id`` (a ValueError
            subclass; the endpoint maps it to 404).
        ValueError -- the scenario is a true negative (verdict=correct: nothing
            to promote) or otherwise cannot be frozen single-axis (-> 422).
        FileExistsError -- a subject already exists at the target path and
            ``overwrite`` is False (I1 immutability).
    """
    scenario, family = _load_scenario(scenario_id)
    if out_root is None:
        out_root = _default_out_root(family)
    manifest, action_log, verdict = _run_typed(scenario, family)
    if verdict != "incorrect":
        raise ValueError(
            f"nothing to promote: scenario {scenario_id!r} is a true negative (verdict=correct)"
        )

    violation_type = scenario["expected"]["violation_type"]
    slug = scenario_id
    subject = to_corpus_subject(manifest, action_log, slug=slug, violation_type=violation_type)

    subject_dir = Path(out_root) / "incorrect" / slug
    manifest_file = subject_dir / _MANIFEST_FILENAME[family]
    actions_file = subject_dir / _ACTIONS_FILENAME[family]
    ground_truth_file = subject_dir / "ground-truth.json"
    targets = [
        (manifest_file, subject["manifest"]),
        (actions_file, subject["actions"]),
        (ground_truth_file, subject["ground-truth"]),
    ]

    if not overwrite:
        for path, _ in targets:
            if path.exists():
                raise FileExistsError(
                    f"subject already exists at {path} (use overwrite to replace)"
                )

    subject_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for path, payload in targets:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        created.append(str(path))

    return {
        "slug": slug,
        "created": created,
        "verdict": verdict,
        "violation_type": violation_type,
    }
