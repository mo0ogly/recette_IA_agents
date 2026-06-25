/**
 * RunsExplorer -- browse the eurodated run registry, view artifacts in Monaco,
 * annotate, replay, and delete runs.
 *
 * Legibility-first: frozen artifacts + sha256 chain are immutable (I1);
 * annotations.json is the only mutable layer (PATCH /results/{id}).
 * Delete purges work-memory (R25) -- never the audit-plane event store.
 */

import { lazy, Suspense, useEffect, useState } from "react";
import {
  fetchRunTree,
  fetchRun,
  fetchRunArtifact,
  patchRunAnnotations,
  deleteRun,
  replayRun,
} from "../../api/client";
import type { RunTree, RunDetail } from "../../api/client";
import RunTreeComponent from "./RunTree";
import PageHelp from "../../components/help/PageHelp";

const MonacoJsonViewer = lazy(() => import("../../components/MonacoJsonViewer"));

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
  const [replayResult, setReplayResult] = useState<RunDetail | null>(null);
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
            <>
              <div className="runs-detail-header">
                <span className="runs-detail-id" data-testid="runs-detail-id">
                  {detail.meta.id}
                </span>
                <span className="runs-detail-kind">{detail.meta.kind}</span>
                <span className="runs-detail-status">{detail.meta.status}</span>
                <button
                  type="button"
                  className="runs-delete-btn"
                  onClick={() => setDeleteConfirmOpen(true)}
                  data-testid="runs-delete-btn"
                >
                  Supprimer
                </button>
              </div>

              {deleteError && (
                <div className="runs-error" role="alert" data-testid="runs-delete-error">
                  {deleteError}
                </div>
              )}

              {deleteConfirmOpen && (
                <div
                  className="runs-confirm-dialog"
                  role="dialog"
                  aria-modal="true"
                  data-testid="runs-confirm-dialog"
                >
                  <p>
                    Supprimer le run <strong>{detail.meta.id}</strong> ?
                    Cette operation archive puis purge le repertoire de travail
                    (R25 -- jamais l&apos;audit store).
                  </p>
                  <button
                    type="button"
                    className="runs-confirm-ok"
                    onClick={handleDelete}
                    data-testid="runs-confirm-ok"
                  >
                    Confirmer la suppression
                  </button>
                  <button
                    type="button"
                    className="runs-confirm-cancel"
                    onClick={() => setDeleteConfirmOpen(false)}
                    data-testid="runs-confirm-cancel"
                  >
                    Annuler
                  </button>
                </div>
              )}

              {/* Artifact selector */}
              {detail.artifacts.length > 1 && (
                <div className="runs-artifact-tabs" data-testid="runs-artifact-tabs">
                  {detail.artifacts.map((name) => (
                    <button
                      key={name}
                      type="button"
                      className={[
                        "runs-artifact-tab",
                        selectedArtifact === name ? "runs-artifact-tab-active" : "",
                      ]
                        .join(" ")
                        .trim()}
                      onClick={() => handleArtifactSelect(name)}
                      data-testid={`runs-artifact-tab-${name}`}
                    >
                      {name}
                    </button>
                  ))}
                </div>
              )}

              {/* Main tabs */}
              <div className="runs-tabs" role="tablist">
                {(["content", "meta", "annotations", "replay"] as TabKey[]).map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    role="tab"
                    className={[
                      "runs-tab",
                      activeTab === tab ? "runs-tab-active" : "",
                    ]
                      .join(" ")
                      .trim()}
                    aria-selected={activeTab === tab}
                    onClick={() => setActiveTab(tab)}
                    data-testid={`runs-tab-${tab}`}
                  >
                    {tab === "content" && "Contenu"}
                    {tab === "meta" && "Meta"}
                    {tab === "annotations" && "Annotations"}
                    {tab === "replay" && "Replay"}
                  </button>
                ))}
              </div>

              {/* Content tab */}
              {activeTab === "content" && (
                <div className="runs-tab-panel" data-testid="runs-panel-content">
                  {artifactError && (
                    <div className="runs-error" role="alert">
                      {artifactError}
                    </div>
                  )}
                  {selectedArtifact && (
                    <div className="runs-monaco-wrapper">
                      <Suspense fallback={<p>Chargement de l&apos;editeur...</p>}>
                        <MonacoJsonViewer
                          value={artifactContent}
                          height="60vh"
                        />
                      </Suspense>
                    </div>
                  )}
                  {!selectedArtifact && (
                    <p className="runs-no-artifact">Aucun artefact disponible.</p>
                  )}
                </div>
              )}

              {/* Meta tab */}
              {activeTab === "meta" && (
                <div className="runs-tab-panel" data-testid="runs-panel-meta">
                  <table className="runs-meta-table">
                    <tbody>
                      <tr>
                        <th scope="row">id</th>
                        <td data-testid="meta-id">{detail.meta.id}</td>
                      </tr>
                      <tr>
                        <th scope="row">kind</th>
                        <td data-testid="meta-kind">{detail.meta.kind}</td>
                      </tr>
                      <tr>
                        <th scope="row">eurodate</th>
                        <td data-testid="meta-eurodate">{detail.meta.eurodate}</td>
                      </tr>
                      <tr>
                        <th scope="row">status</th>
                        <td data-testid="meta-status">{detail.meta.status}</td>
                      </tr>
                      <tr>
                        <th scope="row">parent_group</th>
                        <td>{detail.meta.parent_group}</td>
                      </tr>
                      <tr>
                        <th scope="row">root_hash</th>
                        <td data-testid="meta-root-hash" style={{ fontFamily: "monospace", wordBreak: "break-all" }}>
                          {detail.meta.root_hash}
                        </td>
                      </tr>
                      <tr>
                        <th scope="row">replay_of</th>
                        <td data-testid="meta-replay-of">
                          {detail.meta.replay_of ?? "—"}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                  {detail.meta.artifacts.length > 0 && (
                    <table className="runs-artifacts-table">
                      <thead>
                        <tr>
                          <th>Artefact</th>
                          <th>sha256</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.meta.artifacts.map((a) => (
                          <tr key={a.file}>
                            <td>{a.file}</td>
                            <td
                              data-testid={`meta-sha256-${a.file}`}
                              style={{ fontFamily: "monospace", wordBreak: "break-all" }}
                            >
                              {a.sha256}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}

              {/* Annotations tab */}
              {activeTab === "annotations" && (
                <div className="runs-tab-panel" data-testid="runs-panel-annotations">
                  <div className="runs-annotations-form">
                    <label className="runs-annot-label">
                      Tags (virgule-separated)
                      <input
                        type="text"
                        className="runs-annot-input"
                        value={annotTags}
                        onChange={(e) => setAnnotTags(e.target.value)}
                        data-testid="annot-tags-input"
                      />
                    </label>
                    <label className="runs-annot-label">
                      Commentaire
                      <textarea
                        className="runs-annot-input"
                        value={annotComment}
                        onChange={(e) => setAnnotComment(e.target.value)}
                        data-testid="annot-comment-input"
                        rows={3}
                      />
                    </label>
                    <label className="runs-annot-label">
                      Label
                      <input
                        type="text"
                        className="runs-annot-input"
                        value={annotLabel}
                        onChange={(e) => setAnnotLabel(e.target.value)}
                        data-testid="annot-label-input"
                      />
                    </label>
                    <label className="runs-annot-label">
                      Retention
                      <select
                        className="runs-annot-input"
                        value={annotRetention}
                        onChange={(e) => setAnnotRetention(e.target.value)}
                        data-testid="annot-retention-select"
                      >
                        <option value="keep">keep</option>
                        <option value="purge-after">purge-after</option>
                      </select>
                    </label>
                    <button
                      type="button"
                      className="runs-annot-save"
                      onClick={handleSaveAnnotations}
                      disabled={annotSaving}
                      data-testid="annot-save-btn"
                    >
                      {annotSaving ? "Enregistrement..." : "Enregistrer les annotations"}
                    </button>
                    {annotError && (
                      <div className="runs-error" role="alert" data-testid="annot-error">
                        {annotError}
                      </div>
                    )}
                    {annotSaved && (
                      <div className="runs-success" data-testid="annot-saved">
                        Annotations enregistrees.
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Replay tab */}
              {activeTab === "replay" && (
                <div className="runs-tab-panel" data-testid="runs-panel-replay">
                  <p>
                    Le replay est un <strong>recalcul pur</strong> : il cree un
                    nouveau run enfant (<code>replay_of</code> pointe vers ce run)
                    sans modifier le run parent. Les artefacts du parent sont
                    <strong> immuables</strong> (I1).
                  </p>
                  {detail.meta.replay_of && (
                    <p className="runs-replay-of">
                      Ce run est lui-meme un replay de{" "}
                      <code>{detail.meta.replay_of}</code>.
                    </p>
                  )}
                  <button
                    type="button"
                    className="runs-replay-btn"
                    onClick={handleReplay}
                    disabled={replayBusy}
                    data-testid="replay-btn"
                  >
                    {replayBusy ? "Replay en cours..." : "Lancer le replay"}
                  </button>
                  {replayError && (
                    <div className="runs-error" role="alert" data-testid="replay-error">
                      {replayError.includes("422") || replayError.includes("not replayable")
                        ? "Ce type de run n'est pas rejouable."
                        : replayError}
                    </div>
                  )}
                  {replayResult && (
                    <div className="runs-replay-result" data-testid="replay-result">
                      Run enfant cree : <code>{replayResult.meta.id}</code> (
                      {replayResult.meta.status})
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}
