/**
 * Operator knowledge-base manager: view / insert / delete documents, apply a
 * named poison scenario, reset to the clean baseline.
 *
 * This is the OPERATOR path -- it prepares the RAG poisoning recette. It is NOT
 * an agent action: an agent that wants to mutate the index still escalates
 * through the gateway (ingest_document). The CRUD here never bypasses the
 * Control Plane (I2). Same plain-HTML/CSS style as the retrieval scorecard above.
 */

import { useEffect, useState } from "react";
import {
  addKbDocument,
  applyRagScenario,
  deleteKbDocument,
  listKbDocuments,
  listRagScenarios,
  resetKb,
  type KbDocument,
} from "../../api/client";

const EMPTY_FORM = { id: "", title: "", content: "", tags: "" };

export default function KnowledgeBaseManager(): JSX.Element {
  const [docs, setDocs] = useState<KbDocument[]>([]);
  const [scenarios, setScenarios] = useState<string[]>([]);
  const [scenario, setScenario] = useState<string>("");
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  function refresh(): void {
    Promise.all([listKbDocuments(), listRagScenarios()])
      .then(([d, s]) => {
        setDocs(d);
        setScenarios(s);
        if (s.length > 0 && scenario === "") setScenario(s[0]);
        setLoading(false);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setLoading(false);
      });
  }

  useEffect(refresh, []); // eslint-disable-line react-hooks/exhaustive-deps

  function guarded(action: () => Promise<unknown>): void {
    setBusy(true);
    setError(null);
    action()
      .then(() => {
        setBusy(false);
        refresh();
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setBusy(false);
      });
  }

  function onInsert(e: React.FormEvent): void {
    e.preventDefault();
    guarded(() =>
      addKbDocument({
        id: form.id.trim(),
        title: form.title.trim(),
        content: form.content,
        poisoned: false,
        tags: form.tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      }).then(() => setForm(EMPTY_FORM)),
    );
  }

  return (
    <section className="rag-page" data-testid="kb-manager">
      <h2>Knowledge base</h2>
      <p className="rag-note">
        Operator controls to prepare a poisoning recette: insert or remove documents,
        apply a named poison scenario, then reset to the clean baseline. These never
        bypass the gateway -- an agent that tries to ingest still escalates (I2).
      </p>

      <div className="kb-toolbar">
        <button type="button" disabled={busy} onClick={() => guarded(resetKb)} data-testid="kb-reset">
          Reset to baseline
        </button>
        <select
          aria-label="scenario"
          value={scenario}
          onChange={(e) => setScenario(e.target.value)}
          data-testid="kb-scenario-select"
        >
          {scenarios.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={busy || scenario === ""}
          onClick={() => guarded(() => applyRagScenario(scenario))}
          data-testid="kb-apply"
        >
          Apply scenario
        </button>
      </div>

      {error && (
        <div className="rag-error" role="alert" data-testid="kb-error">
          {error}
        </div>
      )}
      {loading && <p className="rag-loading">Loading knowledge base...</p>}

      {!loading &&
        (docs.length === 0 ? (
          <p className="rag-empty">The knowledge base is empty.</p>
        ) : (
          <table className="rag-table">
            <thead>
              <tr>
                <th>Id</th>
                <th>Title</th>
                <th>Tags</th>
                <th>State</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id} data-testid="kb-row">
                  <td className="rag-ids">{d.id}</td>
                  <td>{d.title}</td>
                  <td>{d.tags.join(", ")}</td>
                  <td>
                    <span className={`rag-pill ${d.poisoned ? "fail" : "ok"}`}>
                      {d.poisoned ? `poison: ${d.threat ?? "?"}` : "clean"}
                    </span>
                  </td>
                  <td>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => guarded(() => deleteKbDocument(d.id))}
                      data-testid="kb-delete"
                    >
                      delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}

      <form className="kb-form" onSubmit={onInsert} data-testid="kb-insert-form">
        <h3>Insert document</h3>
        <input
          aria-label="id"
          placeholder="id"
          required
          value={form.id}
          onChange={(e) => setForm({ ...form, id: e.target.value })}
        />
        <input
          aria-label="title"
          placeholder="title"
          required
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
        />
        <input
          aria-label="tags"
          placeholder="tags (comma-separated)"
          value={form.tags}
          onChange={(e) => setForm({ ...form, tags: e.target.value })}
        />
        <textarea
          aria-label="content"
          placeholder="content"
          required
          value={form.content}
          onChange={(e) => setForm({ ...form, content: e.target.value })}
        />
        <button type="submit" disabled={busy}>
          Insert
        </button>
      </form>
    </section>
  );
}
