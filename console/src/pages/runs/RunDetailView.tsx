/**
 * RunDetailView -- presentational right-pane for RunsExplorer.
 *
 * Receives all state values, setters, and handlers from RunsExplorer via props.
 * Renders: detail header, delete-confirm dialog, artifact selector, main tab bar,
 * and the four tab panels (Content / Meta / Annotations / Replay).
 *
 * No local state, no side-effects. All data-testid strings are preserved verbatim.
 */

import { lazy, Suspense } from "react";
import type { RunDetail, ReplayResult } from "../../api/client";
import AssistButton from "../../components/assist/AssistButton";

const MonacoJsonViewer = lazy(() => import("../../components/MonacoJsonViewer"));

type TabKey = "content" | "meta" | "annotations" | "replay";

export interface RunDetailViewProps {
  detail: RunDetail;

  // Artifact state
  selectedArtifact: string | null;
  artifactContent: string;
  artifactError: string | null;
  onArtifactSelect: (name: string) => void;

  // Tab state
  activeTab: TabKey;
  onTabChange: (tab: TabKey) => void;

  // Annotation state
  annotTags: string;
  annotComment: string;
  annotLabel: string;
  annotRetention: string;
  annotSaving: boolean;
  annotError: string | null;
  annotSaved: boolean;
  setAnnotTags: (v: string) => void;
  setAnnotComment: (v: string) => void;
  setAnnotLabel: (v: string) => void;
  setAnnotRetention: (v: string) => void;
  onSaveAnnotations: () => void;

  // Delete state
  deleteConfirmOpen: boolean;
  deleteError: string | null;
  onDeleteRequest: () => void;
  onDeleteConfirm: () => void;
  onDeleteCancel: () => void;

  // Replay state
  replayResult: ReplayResult | null;
  replayError: string | null;
  replayBusy: boolean;
  onReplay: () => void;
}

export default function RunDetailView({
  detail,
  selectedArtifact,
  artifactContent,
  artifactError,
  onArtifactSelect,
  activeTab,
  onTabChange,
  annotTags,
  annotComment,
  annotLabel,
  annotRetention,
  annotSaving,
  annotError,
  annotSaved,
  setAnnotTags,
  setAnnotComment,
  setAnnotLabel,
  setAnnotRetention,
  onSaveAnnotations,
  deleteConfirmOpen,
  deleteError,
  onDeleteRequest,
  onDeleteConfirm,
  onDeleteCancel,
  replayResult,
  replayError,
  replayBusy,
  onReplay,
}: RunDetailViewProps): JSX.Element {
  return (
    <>
      <div className="runs-detail-header">
        <span className="runs-detail-id" data-testid="runs-detail-id">
          {detail.meta.id}
        </span>
        <span className="runs-detail-kind">{detail.meta.kind}</span>
        <span className="runs-detail-status">{detail.meta.status}</span>
        <AssistButton
          topic="runs.run"
          label={`Detail du run ${detail.meta.id}`}
          params={{ run_id: detail.meta.id }}
        />
        <button
          type="button"
          className="runs-delete-btn"
          onClick={onDeleteRequest}
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
            onClick={onDeleteConfirm}
            data-testid="runs-confirm-ok"
          >
            Confirmer la suppression
          </button>
          <button
            type="button"
            className="runs-confirm-cancel"
            onClick={onDeleteCancel}
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
              onClick={() => onArtifactSelect(name)}
              data-testid={`runs-artifact-tab-${name}`}
            >
              {name}
            </button>
          ))}
        </div>
      )}

      {/* Main tab bar */}
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
            onClick={() => onTabChange(tab)}
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
                <td data-testid="meta-root-hash" className="runs-hash">
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
                      className="runs-hash"
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
              onClick={onSaveAnnotations}
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
            onClick={onReplay}
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
              Run enfant cree : <code>{replayResult.child_run_id}</code> (
              {replayResult.status})
            </div>
          )}
        </div>
      )}
    </>
  );
}
