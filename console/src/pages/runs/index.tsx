/**
 * RunsExplorer -- browse the eurodated run registry, view artifacts in Monaco,
 * annotate, replay, and delete runs.
 *
 * Legibility-first: frozen artifacts + sha256 chain are immutable (I1);
 * annotations.json is the only mutable layer (PATCH /results/{id}).
 * Delete purges work-memory (R25) -- never the audit-plane event store.
 *
 * All state, effects, and handlers live here. Rendering of the right-pane detail
 * block is delegated to RunDetailView (presentational).
 */

import { useEffect, useState } from "react";
import {
  fetchRunTree,
  fetchRun,
  fetchRunArtifact,
  patchRunAnnotations,
  deleteRun,
  replayRun,
} from "../../api/client";
import type { RunTree, RunDetail, ReplayResult } from "../../api/client";
import RunTreeComponent from "./RunTree";
import PageHelp from "../../components/help/PageHelp";
import AssistButton from "../../components/assist/AssistButton";
import RunDetailView from "./RunDetailView";
import "./runs.css";

type TabKey = "content" | "meta" | "annotations" | "replay";

export default function RunsExplorer(): JSX.Element {
  const [tree, setTree] = useState<RunTree | null>(null);
  const [treeError, setTreeError] = useState<string | null>(null);

  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [selectedArtifact, setSelectedArtifact] = useState<string | null>(null);
  const [artifactContent, setArtifactContent] = useState<string>("");
  const [artifactError, setArtifactError] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<TabKey>("content");

  // Annotations edit state
  const [annotTags, setAnnotTags] = useState<string>("");
  const [annotComment, setAnnotComment] = useState<string>("");
  const [annotLabel, setAnnotLabel] = useState<string>("");
  const [annotRetention, setAnnotRetention] = useState<string>("keep");
  const [annotSaving, setAnnotSaving] = useState(false);
  const [annotError, setAnnotError] = useState<string | null>(null);
  const [annotSaved, setAnnotSaved] = useState(false);

  // Delete state
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Replay state
  const [replayResult, setReplayResult] = useState<ReplayResult | null>(null);
  const [replayError, setReplayError] = useState<string | null>(null);
  const [replayBusy, setReplayBusy] = useState(false);

  // Load tree on mount
  useEffect(() => {
    fetchRunTree()
      .then((r) => {
        if (!r) return;
        setTree(r);
      })
      .catch((e: unknown) => {
        setTreeError(e instanceof Error ? e.message : String(e));
      });
  }, []);

  // Load run detail when selection changes
  useEffect(() => {
    if (!selectedRunId) {
      setDetail(null);
      setArtifactContent("");
      setSelectedArtifact(null);
      return;
    }
    setDetailError(null);
    setArtifactError(null);
    fetchRun(selectedRunId)
      .then((r) => {
        if (!r) return;
        setDetail(r);
        // Pre-populate annotation fields
        setAnnotTags(r.annotations.tags.join(", "));
        setAnnotComment(r.annotations.comment);
        setAnnotLabel(r.annotations.label);
        setAnnotRetention(r.annotations.retention);
        setAnnotSaved(false);
        setAnnotError(null);
        setReplayResult(null);
        setReplayError(null);
        setDeleteError(null);
        // Auto-select first artifact
        if (r.artifacts.length > 0) {
          const first = r.artifacts[0];
          setSelectedArtifact(first);
          fetchRunArtifact(selectedRunId, first)
            .then((content) => {
              if (!content) return;
              setArtifactContent(content);
            })
            .catch((e: unknown) => {
              setArtifactError(e instanceof Error ? e.message : String(e));
            });
        } else {
          setArtifactContent("");
          setSelectedArtifact(null);
        }
      })
      .catch((e: unknown) => {
        setDetailError(e instanceof Error ? e.message : String(e));
      });
  }, [selectedRunId]);

  const handleArtifactSelect = (name: string) => {
    if (!selectedRunId) return;
    setSelectedArtifact(name);
    setArtifactError(null);
    fetchRunArtifact(selectedRunId, name)
      .then((content) => {
        if (!content) return;
        setArtifactContent(content);
      })
      .catch((e: unknown) => {
        setArtifactError(e instanceof Error ? e.message : String(e));
      });
  };

  const handleSaveAnnotations = () => {
    if (!selectedRunId) return;
    setAnnotSaving(true);
    setAnnotError(null);
    setAnnotSaved(false);
    patchRunAnnotations(selectedRunId, {
      tags: annotTags
        .split(",")
        .map((t) => t.trim())
        .filter((t) => t.length > 0),
      comment: annotComment,
      label: annotLabel,
      retention: annotRetention,
    })
      .then((r) => {
        if (!r) return;
        setDetail(r);
        setAnnotSaved(true);
      })
      .catch((e: unknown) => {
        setAnnotError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => setAnnotSaving(false));
  };

  const handleDelete = () => {
    if (!selectedRunId) return;
    setDeleteError(null);
    deleteRun(selectedRunId)
      .then(() => {
        setDeleteConfirmOpen(false);
        setSelectedRunId(null);
        setDetail(null);
        // Refresh tree
        return fetchRunTree();
      })
      .then((r) => {
        if (!r) return;
        setTree(r);
      })
      .catch((e: unknown) => {
        setDeleteError(e instanceof Error ? e.message : String(e));
        setDeleteConfirmOpen(false);
      });
  };

  const handleReplay = () => {
    if (!selectedRunId) return;
    setReplayBusy(true);
    setReplayError(null);
    setReplayResult(null);
    replayRun(selectedRunId)
      .then((r) => {
        if (!r) return;
        setReplayResult(r);
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : String(e);
        // 422 = not replayable for this kind
        setReplayError(msg);
      })
      .finally(() => setReplayBusy(false));
  };

  return (
    <div className="runs-explorer" data-testid="runs-explorer">
      <div className="runs-explorer-header">
        <h2 className="runs-explorer-title">Explorateur de runs</h2>
        <PageHelp topic="runs_explorer" />
        <AssistButton topic="runs.recent" label="Runs recents" />
      </div>

      <div className="runs-explorer-body">
        {/* Left pane: tree */}
        <aside className="runs-explorer-sidebar" data-testid="runs-sidebar">
          {treeError && (
            <div className="runs-error" role="alert" data-testid="runs-tree-error">
              {treeError}
            </div>
          )}
          {tree ? (
            <RunTreeComponent
              data={tree}
              selectedId={selectedRunId}
              onSelect={(id) => {
                setSelectedRunId(id);
                setActiveTab("content");
              }}
            />
          ) : !treeError ? (
            <p className="runs-loading">Chargement...</p>
          ) : null}
        </aside>

        {/* Right pane: detail */}
        <main className="runs-explorer-main" data-testid="runs-main">
          {!selectedRunId && (
            <p className="runs-placeholder">
              Selectionnez un run dans l&apos;arborescence.
            </p>
          )}

          {detailError && (
            <div className="runs-error" role="alert" data-testid="runs-detail-error">
              {detailError}
            </div>
          )}

          {detail && (
            <RunDetailView
              detail={detail}
              selectedArtifact={selectedArtifact}
              artifactContent={artifactContent}
              artifactError={artifactError}
              onArtifactSelect={handleArtifactSelect}
              activeTab={activeTab}
              onTabChange={setActiveTab}
              annotTags={annotTags}
              annotComment={annotComment}
              annotLabel={annotLabel}
              annotRetention={annotRetention}
              annotSaving={annotSaving}
              annotError={annotError}
              annotSaved={annotSaved}
              setAnnotTags={setAnnotTags}
              setAnnotComment={setAnnotComment}
              setAnnotLabel={setAnnotLabel}
              setAnnotRetention={setAnnotRetention}
              onSaveAnnotations={handleSaveAnnotations}
              deleteConfirmOpen={deleteConfirmOpen}
              deleteError={deleteError}
              onDeleteRequest={() => setDeleteConfirmOpen(true)}
              onDeleteConfirm={handleDelete}
              onDeleteCancel={() => setDeleteConfirmOpen(false)}
              replayResult={replayResult}
              replayError={replayError}
              replayBusy={replayBusy}
              onReplay={handleReplay}
            />
          )}
        </main>
      </div>
    </div>
  );
}
