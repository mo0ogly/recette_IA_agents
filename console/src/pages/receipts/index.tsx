/**
 * Context receipts page: a privacy-safe, content-free audit of what crossed the
 * agent<->server boundary.
 *
 * Each recorded side effect (ProxyTrace) is shown as a receipt: the intent
 * metadata (agent, target, action, resource, outcome) plus the request/response
 * body byte-size and SHA-256 -- never the bodies. An auditor proves WHAT crossed
 * and that it is unchanged, without the platform exposing the content. Read-only.
 */

import { useEffect, useState } from "react";

import {
  exportContextReceipts,
  getContextReceipts,
  verifyContextReceipts,
  verifyImportedReceipts,
  type ReceiptImportVerdict,
} from "../../api/client";
import PageHelp from "../../components/help/PageHelp";
import AssistButton from "../../components/assist/AssistButton";
import type { ChainReport, ContextReceipt } from "../../types/platform";
import "./receipts.css";

function shortHash(h: string): string {
  return h ? `${h.slice(0, 12)}…` : "—";
}

export default function ReceiptsPage(): JSX.Element {
  const [receipts, setReceipts] = useState<ContextReceipt[] | null>(null);
  const [chain, setChain] = useState<ChainReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [importVerdict, setImportVerdict] = useState<ReceiptImportVerdict | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  function readFileText(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error ?? new Error("file read failed"));
      reader.readAsText(file);
    });
  }

  async function handleImport(file: File): Promise<void> {
    setImportVerdict(null);
    setImportError(null);
    try {
      const envelope: unknown = JSON.parse(await readFileText(file));
      const verdict = await verifyImportedReceipts(envelope);
      setImportVerdict(verdict);
    } catch (e: unknown) {
      setImportError(String(e));
    }
  }

  async function handleExport(): Promise<void> {
    setExporting(true);
    try {
      const envelope = await exportContextReceipts();
      const blob = new Blob([JSON.stringify(envelope, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "context-receipts-export.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      setError(String(e));
    } finally {
      setExporting(false);
    }
  }

  useEffect(() => {
    getContextReceipts()
      .then((r) => setReceipts(r.receipts))
      .catch((e: unknown) => setError(String(e)))
      .finally(() => setLoading(false));
    verifyContextReceipts()
      .then(setChain)
      .catch(() => setChain(null));
  }, []);

  return (
    <section className="page receipts-page">
      <div className="page-head">
        <h1>Context receipts</h1>
        <PageHelp topic="receipts" />
        <AssistButton topic="audit.recent" label="Journal d'audit recent" />
        {chain !== null && (
          <span
            className={`receipts-chain receipts-chain-${chain.ok ? "ok" : "broken"}`}
            data-testid="receipts-chain"
            title="Preuve d'integrite de sequence (hash chain, comme l'audit log I1)"
          >
            {chain.ok
              ? `chaine verifiee (${chain.checked})`
              : `chaine rompue @ seq ${chain.first_break_seq}`}
          </span>
        )}
      </div>
      <p className="receipts-note">
        Audit <strong>sans contenu</strong> de ce qui a franchi la frontiere agent &lt;-&gt;
        serveur. Chaque effet de bord est un <strong>recu</strong> : l&apos;intention (agent,
        cible, action, ressource, issue) + la <strong>taille</strong> et le{" "}
        <strong>SHA-256</strong> des corps requete/reponse -- <strong>jamais les corps</strong>.
        Prouve ce qui a traverse, sans exposer le contenu (RSSI-safe). Lecture seule.
      </p>
      <div className="receipts-actions">
        <button
          type="button"
          className="receipts-export"
          disabled={exporting || (receipts?.length ?? 0) === 0}
          onClick={() => void handleExport()}
        >
          {exporting ? "Export..." : "Exporter (signe Ed25519)"}
        </button>
        <label className="receipts-import">
          Verifier un export tiers
          <input
            type="file"
            accept="application/json,.json"
            data-testid="receipts-import-input"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleImport(file);
            }}
          />
        </label>
      </div>
      {loading && <p className="receipts-loading">Chargement des receipts...</p>}

      {importError !== null && <p className="receipts-error">{importError}</p>}
      {importVerdict !== null && (
        <p
          className={`receipts-verdict receipts-verdict-${
            importVerdict.signature.valid && importVerdict.chain.ok ? "ok" : "bad"
          }`}
          data-testid="receipts-import-verdict"
        >
          <strong>Signature</strong>{" "}
          {importVerdict.signature.valid ? "valide" : `invalide -- ${importVerdict.signature.reason}`}
          {" / "}
          <strong>Chaine</strong>{" "}
          {importVerdict.chain.ok
            ? `verifiee (${importVerdict.chain.checked})`
            : `rompue @ seq ${importVerdict.chain.first_break_seq}`}
        </p>
      )}
      {error !== null && <p className="receipts-error">{error}</p>}
      {receipts !== null &&
        (receipts.length === 0 ? (
          <p className="receipts-empty">
            Aucun recu -- lance un agent (les effets de bord sont traces ici).
          </p>
        ) : (
          <table className="receipts-table" data-testid="receipts-table">
            <thead>
              <tr>
                <th>agent</th>
                <th>action</th>
                <th>cible</th>
                <th>statut</th>
                <th>req</th>
                <th>req sha256</th>
                <th>resp</th>
                <th>resp sha256</th>
              </tr>
            </thead>
            <tbody>
              {receipts.map((r) => (
                <tr key={r.event_id ?? r.seq} className={r.ok === false ? "receipts-row-fail" : ""}>
                  <td className="receipts-id">{r.agent_id}</td>
                  <td>{r.action_type}</td>
                  <td>
                    {r.target} / {r.resource}
                  </td>
                  <td>{r.status_code}</td>
                  <td className="receipts-num">{r.request_bytes} o</td>
                  <td className="receipts-hash" title={r.request_sha256}>
                    {shortHash(r.request_sha256)}
                  </td>
                  <td className="receipts-num">{r.response_bytes} o</td>
                  <td className="receipts-hash" title={r.response_sha256}>
                    {shortHash(r.response_sha256)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
    </section>
  );
}
