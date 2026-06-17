/**
 * One registry agent, rendered as a card: name + version, publisher,
 * description, tags and the declared tool count. A tool-less agent
 * (tool_count 0) is marked distinctly -- a discovery edge case the catalog
 * must surface, not hide. Presentational: the parent supplies the agent.
 */

import type { CatalogAgentSummary } from "../../types/platform";

export default function RegistryAgentCard({
  agent,
}: {
  agent: CatalogAgentSummary;
}): JSX.Element {
  const silent = agent.tool_count === 0;
  return (
    <article
      className={`registry-agent ${silent ? "registry-agent-silent" : ""}`}
      data-testid={`registry-agent-${agent.name}`}
    >
      <header className="registry-agent-head">
        <span className="registry-agent-name">{agent.name}</span>
        <span className="registry-agent-version">v{agent.version}</span>
      </header>
      <p className="registry-agent-publisher">par {agent.publisher_name}</p>
      <p className="registry-agent-desc">{agent.description}</p>
      <div className="registry-agent-foot">
        <div className="registry-agent-tags">
          {agent.tags.length > 0 ? (
            agent.tags.map((tag) => (
              <span key={tag} className="registry-tag">
                {tag}
              </span>
            ))
          ) : (
            <span className="registry-agent-notags">aucun tag</span>
          )}
        </div>
        <span
          className={`registry-chip ${silent ? "registry-chip-silent" : "registry-chip-tools"}`}
          data-testid={`registry-agent-tools-${agent.name}`}
        >
          {silent ? "aucun outil" : `${agent.tool_count} outils`}
        </span>
      </div>
    </article>
  );
}
