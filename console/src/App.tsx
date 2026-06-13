import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import AgentsPage from "./pages/agents";
import ApprovalsPage from "./pages/approvals";
import AuditPage from "./pages/audit";
import CatalogPage from "./pages/catalog";
import CampaignsPage from "./pages/campaigns";
import CockpitPage from "./pages/cockpit";
import CorpusPage from "./pages/corpus";
import SimPage from "./pages/sim";
import DashboardPage from "./pages/dashboard";
import DiscoveryPage from "./pages/discovery";
import FluxPage from "./pages/flux";
import ProxyNavBadge from "./components/ProxyNavBadge";
import ProxyPage from "./pages/proxy";
import RagPage from "./pages/rag";
import RecettePage from "./pages/recette";
import ServersPage from "./pages/servers";
import VerdictsPage from "./pages/verdicts";

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "nav-link nav-link-active" : "nav-link";
}

export default function App(): JSX.Element {
  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="app-title">AgentRail Recette</span>
        <nav className="app-nav">
          <NavLink to="/dashboard" className={navLinkClass}>
            Tableau de bord
          </NavLink>
          <NavLink to="/cockpit" className={navLinkClass}>
            Cockpit
          </NavLink>
          <NavLink to="/flux" className={navLinkClass}>
            Flux
          </NavLink>
          <NavLink to="/recette" className={navLinkClass}>
            Recette
          </NavLink>
          <NavLink to="/campaigns" className={navLinkClass}>
            Campagnes
          </NavLink>
          <NavLink to="/verdicts" className={navLinkClass}>
            Verdicts
          </NavLink>
          <NavLink to="/rag" className={navLinkClass}>
            RAG
          </NavLink>
          <NavLink to="/discovery" className={navLinkClass}>
            Discovery
          </NavLink>
          <NavLink to="/corpus" className={navLinkClass}>
            Corpus
          </NavLink>
          <NavLink to="/sim" className={navLinkClass}>
            Red-team
          </NavLink>
          <NavLink to="/agents" className={navLinkClass}>
            Agents
          </NavLink>
          <NavLink to="/servers" className={navLinkClass}>
            Serveurs
          </NavLink>
          <span className="nav-sep">Gouvernance (mock)</span>
          <NavLink to="/catalog" className={navLinkClass}>
            Catalog
          </NavLink>
          <NavLink to="/approvals" className={navLinkClass}>
            Approvals
          </NavLink>
          <NavLink to="/audit" className={navLinkClass}>
            Audit
          </NavLink>
          <NavLink to="/proxy" className={navLinkClass}>
            Proxy
            <ProxyNavBadge />
          </NavLink>
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/cockpit" element={<CockpitPage />} />
          <Route path="/flux" element={<FluxPage />} />
          <Route path="/recette" element={<RecettePage />} />
          <Route path="/campaigns" element={<CampaignsPage />} />
          <Route path="/verdicts" element={<VerdictsPage />} />
          <Route path="/rag" element={<RagPage />} />
          <Route path="/discovery" element={<DiscoveryPage />} />
          <Route path="/corpus" element={<CorpusPage />} />
          <Route path="/sim" element={<SimPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/servers" element={<ServersPage />} />
          <Route path="/catalog" element={<CatalogPage />} />
          <Route path="/approvals" element={<ApprovalsPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/proxy" element={<ProxyPage />} />
        </Routes>
      </main>
    </div>
  );
}
