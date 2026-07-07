/**
 * Agent registry page: the generated registry of corpus subjects + metadata.
 *
 * A read-only, GENERATED aggregate (auto-registry-on-merge, microsoft/discovery
 * style): one row per corpus subject with identity, kind/family, version,
 * target systems, capability count, import provenance and the optional registry
 * metadata (publisher / compliance / party / tags). A party filter narrows the
 * view. The registry is derived, never hand-authored.
 */

import { useEffect, useMemo, useState } from "react";

import { getAgentRegistry } from "../../api/client";
import PageHelp from "../../components/help/PageHelp";
import AssistButton from "../../components/assist/AssistButton";
import type { AgentRegistry, RegistryAgent } from "../../types/platform";
import "./agent-registry.css";

export default function AgentRegistryPage(): JSX.Element {
  const [registry, setRegistry] = useState<AgentRegistry | null>(null);
  const [party, setParty] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAgentRegistry()
      .then(setRegistry)
      .catch((e: unknown) => setError(String(e)));
  }, []);

  const rows: RegistryAgent[] = useMemo(() => {
    const all = registry?.agents ?? [];
    return party === "all" ? all : all.filter((a) => a.party === party);
  }, [registry, party]);

  return (
    <section className="page registry-page">
      <div className="page-head">
        <h1>Agent registry</h1>
        <PageHelp topic="agent_registry" />
        <AssistButton topic="agents.list" label="Agents connus" />
      </div>
      <p className="registry-note">
        Registre <strong>genere</strong> des sujets du corpus (jamais ecrit a la main) : identite,
        kind/famille, version, systemes cibles, capacites, provenance d&apos;import et les{" "}
        <strong>metadonnees</strong> optionnelles (publisher / compliance / party / tags). Lecture
        seule.
      </p>

      <div className="registry-filter">
        <label htmlFor="registry-party">Party</label>
        <select id="registry-party" value={party} onChange={(e) => setParty(e.target.value)}>
          <option value="all">tous</option>
          <option value="1p">1p (first-party)</option>
          <option value="3p">3p (third-party)</option>
        </select>
        {registry && <span className="registry-count">{rows.length} agent(s)</span>}
      </div>

      {error && <p className="registry-error">{error}</p>}

      {registry !== null && (
        <table className="registry-table" data-testid="registry-table">
          <thead>
            <tr>
              <th>agent</th>
              <th>kind</th>
              <th>version</th>
              <th>party</th>
              <th>compliance</th>
              <th>publisher</th>
              <th>tags</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.agent_id}>
                <td className="registry-id">{a.agent_id}</td>
                <td>{a.kind}</td>
                <td>{a.version ?? "—"}</td>
                <td>
                  {a.party ? (
                    <span className={`registry-party registry-party-${a.party}`}>{a.party}</span>
                  ) : (
                    "—"
                  )}
                </td>
                <td>{a.compliance.length ? a.compliance.join(", ") : "—"}</td>
                <td>{a.publisher ?? "—"}</td>
                <td>{a.tags.length ? a.tags.join(", ") : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
