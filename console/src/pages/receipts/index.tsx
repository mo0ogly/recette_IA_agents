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

import { getContextReceipts, verifyContextReceipts } from "../../api/client";
import PageHelp from "../../components/help/PageHelp";
import type { ChainReport, ContextReceipt } from "../../types/platform";
import "./receipts.css";

function shortHash(h: string): string {
  return h ? `${h.slice(0, 12)}…` : "—";
}

export default function ReceiptsPage(): JSX.Element {
  const [receipts, setReceipts] = useState<ContextReceipt[] | null>(null);
  const [chain, setChain] = useState<ChainReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getContextReceipts()
      .then((r) => setReceipts(r.receipts))
      .catch((e: unknown) => setError(String(e)));
    verifyContextReceipts()
      .then(setChain)
      .catch(() => setChain(null));
  }, []);

  return (
    <section className="page receipts-page">
      <div className="page-head">
        <h1>Context receipts</h1>
        <PageHelp topic="receipts" />
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
      {error && <p className="receipts-error">{error}</p>}
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
