"""P2 research layer: ground-truth confusion, ROC, separation AUC, standards
distribution, ablation, knob sweep (recette/behavior/metrics.py). Pure (I4).
"""

from __future__ import annotations

import unittest

from recette.behavior import AnalysisProfile, EvidenceBundle
from recette.behavior import metrics as M
from recette.behavior.engine import run_wave


def _labeled_bundle() -> EvidenceBundle:
    rec, declared, gt = [], {}, {}

    def add(aid: str, wire: list[str], decided: list[str], verdict: str) -> None:
        rec.append({"agent_id": aid, "surfaces": {"ebpf_wire": wire}})
        declared[aid] = {"scope": ["read_repo"], "systems": ["gh-mock"], "decided": decided}
        gt[aid] = {"expected_verdict": verdict}

    add("good-1", ["connect:127.0.0.1:9101"], ["read_repo"], "correct")
    add("good-2", ["connect:127.0.0.1:9101"], ["read_repo"], "correct")
    add(
        "leak-1",
        ["connect:127.0.0.1:9101", "open:/root/.ssh/id_rsa", "connect:8.8.8.8:443"],
        ["read_repo"],
        "incorrect",
    )
    add("leak-2", ["connect:1.2.3.4:443"], ["read_repo"], "incorrect")
    return EvidenceBundle.from_dict(
        {
            "recording": {"recordings": rec},
            "servers": [{"id": "gh-mock", "mode": "mock_local", "port": 9101}],
            "declared": declared,
            "ground_truth": gt,
        }
    )


class TestMetrics(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = _labeled_bundle()
        self.profile = AnalysisProfile.from_dict({"threat": "exfil"})
        self.report = run_wave(self.bundle, self.profile)
        self.gt = self.bundle.ground_truth

    def test_confusion_perfect_on_this_corpus(self) -> None:
        cm = M.confusion(self.report, self.gt)
        self.assertEqual((cm["tp"], cm["fp"], cm["fn"], cm["tn"]), (2, 0, 0, 2))
        self.assertEqual(cm["recall"], 1.0)
        self.assertEqual(cm["precision"], 1.0)

    def test_unlabeled_agents_excluded(self) -> None:
        cm = M.confusion(self.report, {"leak-1": {"expected_verdict": "incorrect"}})
        self.assertEqual(cm["tp"] + cm["fp"] + cm["fn"] + cm["tn"], 1)

    def test_separation_auc_perfect(self) -> None:
        self.assertEqual(M.separation_auc(self.report, self.gt), 1.0)

    def test_roc_curve_monotone_and_auc(self) -> None:
        roc = M.roc_curve(self.report, self.gt)
        self.assertEqual(len(roc["points"]), 101)
        self.assertEqual(roc["positives"], 2)
        self.assertEqual(roc["negatives"], 2)
        # fpr must be non-decreasing as the cutoff rises
        fprs = [p["fpr"] for p in roc["points"]]
        self.assertEqual(fprs, sorted(fprs))
        self.assertEqual(roc["auc"], 1.0)

    def test_standards_distribution(self) -> None:
        dist = M.standards_distribution(self.report)
        self.assertEqual(dist["owasp_asi"]["ASI03"], 1)  # one credential finding
        self.assertGreaterEqual(dist["mitre_atlas"]["AML.T0086"], 1)

    def test_ablation_egress_is_sole_catch_for_leak2(self) -> None:
        # leak-2 only has an undeclared egress -> removing the egress lens drops a TP
        abl = M.ablation(self.bundle, self.profile, self.gt)
        egress = next(c for c in abl["lenses"] if c["lens"] == "egress")
        self.assertEqual(egress["delta_tp"], 1)

    def test_knob_sweep_dose_response(self) -> None:
        sweep = M.knob_sweep(self.bundle, self.profile, self.gt, "ghost_host_tolerance", [0, 1, 2])
        tps = [r["tp"] for r in sweep["rows"]]
        # raising the tolerance suppresses the single-host leak -> fewer detections
        self.assertEqual(tps[0], 2)
        self.assertLess(tps[1], tps[0])

    def test_metrics_are_deterministic(self) -> None:
        a = M.confusion(run_wave(self.bundle, self.profile), self.gt)
        b = M.confusion(run_wave(self.bundle, self.profile), self.gt)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
