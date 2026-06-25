"""Research layer -- turn a wave into MEASUREMENTS, not just findings.

Given an ``AnalysisReport`` (or a bundle+profile) and the bundle's ground-truth
labels, compute the things a researcher publishes: a confusion matrix, a ROC curve
over the behavioral-score cutoff, a separation AUC, per-lens ablation, a knob
sweep, and a standards distribution. All pure (I4): deterministic, sorted, no
clock/random -- so a reproduced run yields identical metrics.

Label convention: an agent whose ground-truth ``expected_verdict`` is
``"incorrect"`` is a POSITIVE (it SHOULD be detected); ``"correct"`` is a NEGATIVE
(it should stay clean). Agents without a ground-truth label are excluded from the
metrics (you cannot score what you did not label).
"""

from __future__ import annotations

from .engine import run_wave
from .evidence import EvidenceBundle
from .profile import AnalysisProfile
from .report import AnalysisReport


def _labels(ground_truth: dict[str, dict]) -> dict[str, bool]:
    """agent_id -> is_positive (expected incorrect). Unlabeled agents are dropped."""
    out: dict[str, bool] = {}
    for agent_id, gt in ground_truth.items():
        verdict = gt.get("expected_verdict")
        if verdict in ("correct", "incorrect"):
            out[agent_id] = verdict == "incorrect"
    return out


def _safe_div(num: float, den: float) -> float:
    return round(num / den, 6) if den else 0.0


def confusion(
    report: AnalysisReport,
    ground_truth: dict[str, dict],
    *,
    cutoff: int | None = None,
) -> dict:
    """Confusion matrix + precision/recall/F1/accuracy. Detection rule: ``cutoff``
    None -> an agent is detected when its report is DIVERGENT (not coherent);
    otherwise an agent is detected when ``behavioral_score <= cutoff`` (the ROC
    decision threshold)."""
    labels = _labels(ground_truth)
    by_id = {a.agent_id: a for a in report.agents}
    tp = fp = fn = tn = 0
    for agent_id, is_pos in sorted(labels.items()):
        ar = by_id.get(agent_id)
        if ar is None:
            continue
        detected = (not ar.coherent) if cutoff is None else (ar.behavioral_score <= cutoff)
        if is_pos and detected:
            tp += 1
        elif is_pos and not detected:
            fn += 1
        elif not is_pos and detected:
            fp += 1
        else:
            tn += 1
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": _safe_div(2 * precision * recall, precision + recall),
        "accuracy": _safe_div(tp + tn, tp + fp + fn + tn),
    }


def roc_curve(report: AnalysisReport, ground_truth: dict[str, dict]) -> dict:
    """ROC over the behavioral-score cutoff (0..100), from a SINGLE wave. A lower
    score is more suspicious, so detection at cutoff c is ``score <= c``. Returns
    sorted ``points`` ``[{cutoff, tpr, fpr, tp, fp}]`` and a trapezoidal ``auc``."""
    labels = _labels(ground_truth)
    by_id = {a.agent_id: a for a in report.agents}
    pos = [by_id[a].behavioral_score for a, p in labels.items() if p and a in by_id]
    neg = [by_id[a].behavioral_score for a, p in labels.items() if not p and a in by_id]
    n_pos, n_neg = len(pos), len(neg)
    points = []
    for cutoff in range(0, 101):
        tp = sum(1 for s in pos if s <= cutoff)
        fp = sum(1 for s in neg if s <= cutoff)
        points.append(
            {
                "cutoff": cutoff,
                "tpr": _safe_div(tp, n_pos),
                "fpr": _safe_div(fp, n_neg),
                "tp": tp,
                "fp": fp,
            }
        )
    # trapezoidal AUC over (fpr, tpr) as cutoff sweeps low->high (fpr non-decreasing)
    auc = 0.0
    for a, b in zip(points, points[1:], strict=False):
        auc += (b["fpr"] - a["fpr"]) * (a["tpr"] + b["tpr"]) / 2
    return {"points": points, "auc": round(auc, 6), "positives": n_pos, "negatives": n_neg}


def separation_auc(report: AnalysisReport, ground_truth: dict[str, dict]) -> float:
    """Rank-based AUC: the probability a random POSITIVE is scored more suspicious
    (lower behavioral_score) than a random NEGATIVE. 1.0 = perfect separation,
    0.5 = no better than chance. Ties count as half. Deterministic."""
    labels = _labels(ground_truth)
    by_id = {a.agent_id: a for a in report.agents}
    pos = [by_id[a].behavioral_score for a, p in labels.items() if p and a in by_id]
    neg = [by_id[a].behavioral_score for a, p in labels.items() if not p and a in by_id]
    if not pos or not neg:
        return 0.0
    wins = 0.0
    for ps in pos:
        for ns in neg:
            if ps < ns:
                wins += 1.0
            elif ps == ns:
                wins += 0.5
    return round(wins / (len(pos) * len(neg)), 6)


def standards_distribution(report: AnalysisReport) -> dict:
    """Count findings by OWASP ASI and MITRE ATLAS tag across the wave (sorted)."""
    owasp: dict[str, int] = {}
    atlas: dict[str, int] = {}
    for a in report.agents:
        for f in a.findings:
            if f.owasp_asi:
                owasp[f.owasp_asi] = owasp.get(f.owasp_asi, 0) + 1
            if f.mitre_atlas:
                atlas[f.mitre_atlas] = atlas.get(f.mitre_atlas, 0) + 1
    return {
        "owasp_asi": dict(sorted(owasp.items())),
        "mitre_atlas": dict(sorted(atlas.items())),
    }


def ablation(
    bundle: EvidenceBundle, profile: AnalysisProfile, ground_truth: dict[str, dict]
) -> dict:
    """Per-lens contribution: the confusion with the full profile, then with each
    lens removed -> the delta in true/false positives. A lens that, when removed,
    drops TP is pulling its weight; one that only drops FP is a noise source."""
    base = run_wave(bundle, profile)
    base_cm = confusion(base, ground_truth)
    contributions = []
    for lens_name in profile.lenses:
        reduced = AnalysisProfile(
            name=f"{profile.name}-no-{lens_name}",
            lenses=tuple(name_ for name_ in profile.lenses if name_ != lens_name),
            thresholds=profile.thresholds,
            cohort=profile.cohort,
            threat=profile.threat,
        )
        cm = confusion(run_wave(bundle, reduced), ground_truth)
        contributions.append(
            {
                "lens": lens_name,
                "delta_tp": base_cm["tp"] - cm["tp"],
                "delta_fp": base_cm["fp"] - cm["fp"],
                "delta_recall": round(base_cm["recall"] - cm["recall"], 6),
            }
        )
    contributions.sort(key=lambda c: (-c["delta_tp"], c["lens"]))
    return {"base": base_cm, "lenses": contributions}


def knob_sweep(
    bundle: EvidenceBundle,
    profile: AnalysisProfile,
    ground_truth: dict[str, dict],
    knob: str,
    values: list,
) -> dict:
    """Sweep a threshold knob across ``values``, re-running the wave each time, and
    record the confusion at each setting -- the parametrable 'wave variation' a
    researcher uses to find the operating point (e.g. ghost_host_tolerance 0..5)."""
    rows = []
    for value in values:
        thresholds = dict(profile.thresholds)
        thresholds[knob] = value
        prof = AnalysisProfile(
            name=f"{profile.name}-{knob}={value}",
            lenses=profile.lenses,
            thresholds=thresholds,
            cohort=profile.cohort,
            threat=profile.threat,
        )
        cm = confusion(run_wave(bundle, prof), ground_truth)
        rows.append({"value": value, **cm})
    return {"knob": knob, "rows": rows}
