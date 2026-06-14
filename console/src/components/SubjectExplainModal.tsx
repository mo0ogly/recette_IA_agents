/**
 * SubjectExplainModal -- explains a corpus subject in tabs: its declared
 * manifest, its ground-truth posture (four recette dimensions + verdict), and
 * the raw JSON. Source: GET /subjects/{id} (full manifest + ground_truth).
 */
import { useEffect, useState } from "react";
import { getSubjectDetail } from "../api/client";
import type { SubjectDetail } from "../api/client";
import TabbedModal from "./TabbedModal";
import type { Tab } from "./TabbedModal";
import { GroundTruthView, ManifestView, RawJson } from "./explainViews";

interface Props {
  open: boolean;
  subjectId: string | null;
  onClose: () => void;
}

export default function SubjectExplainModal({ open, subjectId, onClose }: Props): JSX.Element | null {
  const [detail, setDetail] = useState<SubjectDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDetail(null);
    setError(null);
    if (!open || subjectId === null) return;
    setLoading(true);
    let alive = true;
    void getSubjectDetail(subjectId)
      .then((d) => {
        if (alive) setDetail(d);
      })
      .catch((e) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [open, subjectId]);

  if (!open || subjectId === null) return null;

  if (loading || error !== null || detail === null) {
    const note = loading ? `Chargement de ${subjectId}...` : (error ?? "Sujet introuvable.");
    const tabs: Tab[] = [{ key: "state", label: "Sujet", content: <p className="tm-empty">{note}</p> }];
    return <TabbedModal open={open} title={`Sujet -- ${subjectId}`} tabs={tabs} onClose={onClose} />;
  }

  const tabs: Tab[] = [
    { key: "manifest", label: "Manifest", content: <ManifestView manifest={detail.manifest} /> },
    {
      key: "ground-truth",
      label: "Ground-truth",
      content: <GroundTruthView groundTruth={detail.ground_truth} />,
    },
    {
      key: "json",
      label: "JSON",
      content: <RawJson value={{ manifest: detail.manifest, ground_truth: detail.ground_truth }} />,
    },
  ];

  return <TabbedModal open={open} title={`Sujet -- ${subjectId}`} tabs={tabs} onClose={onClose} />;
}
