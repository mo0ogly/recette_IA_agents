import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import AgentsPage from "./pages/agents";
import AiBackendsPage from "./pages/ai-backends";
import ApprovalsPage from "./pages/approvals";
import AuditPage from "./pages/audit";
import CatalogPage from "./pages/catalog";
import ControlPage from "./pages/control";
import MetricsPage from "./pages/metrics";
import CampaignsPage from "./pages/campaigns";
import CorpusPage from "./pages/corpus";
import SimPage from "./pages/sim";
import DashboardPage from "./pages/dashboard";
import DetectPage from "./pages/detect";
import DiscoveryPage from "./pages/discovery";
import FluxPage from "./pages/flux";
import LivePage from "./pages/live";
import ObservabilityPage from "./pages/observability";
import ProbePage from "./pages/probe";
import ProxyNavBadge from "./components/ProxyNavBadge";
import ProxyPage from "./pages/proxy";
import RagPage from "./pages/rag";
import RecettePage from "./pages/recette";
import RegistryPage from "./pages/registry";
import RecetteCampaignsPage from "./pages/recette-campaigns";
import ServersPage from "./pages/servers";
import VerdictsPage from "./pages/verdicts";

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "nav-link nav-link-active" : "nav-link";
}

export default function App(): JSX.Element {
  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="app-title">inspect_ia_agents</span>
        <nav className="app-nav">
          <NavLink to="/dashboard" className={navLinkClass}>
            Tableau de bord
          </NavLink>
          <NavLink to="/flux" className={navLinkClass}>
            Flux
          </NavLink>
          <NavLink to="/live" className={navLinkClass}>
            Temps reel
          </NavLink>
          <NavLink to="/recette" className={navLinkClass}>
            Recette
          </NavLink>
          <NavLink to="/campaigns" className={navLinkClass}>
            Campagnes
          </NavLink>
          <NavLink to="/recette-campaigns" className={navLinkClass}>
            Campagnes recette
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
          <NavLink to="/detect" className={navLinkClass}>
            Reperage
          </NavLink>
          <NavLink to="/registry" className={navLinkClass}>
            Catalogue
          </NavLink>
          <NavLink to="/probe" className={navLinkClass}>
            Probe
          </NavLink>
          <NavLink to="/sim" className={navLinkClass}>
            Red-team
          </NavLink>
          <NavLink to="/agents" className={navLinkClass}>
            Agents
          </NavLink>
          <NavLink to="/ai-backends" className={navLinkClass}>
            IA
          </NavLink>
          <NavLink to="/servers" className={navLinkClass}>
            Serveurs
          </NavLink>
          <span className="nav-sep">Control plane</span>
          <NavLink to="/control" className={navLinkClass}>
            Control
          </NavLink>
          <NavLink to="/catalog" className={navLinkClass}>
            Catalog
          </NavLink>
          <NavLink to="/approvals" className={navLinkClass}>
            Approvals
          </NavLink>
          <NavLink to="/audit" className={navLinkClass}>
            Audit
          </NavLink>
          <NavLink to="/observability" className={navLinkClass}>
            Observabilite
          </NavLink>
          <NavLink to="/metrics" className={navLinkClass}>
            Metriques
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
          <Route path="/cockpit" element={<Navigate to="/agents" replace />} />
          <Route path="/flux" element={<FluxPage />} />
          <Route path="/live" element={<LivePage />} />
          <Route path="/recette" element={<RecettePage />} />
          <Route path="/campaigns" element={<CampaignsPage />} />
          <Route path="/recette-campaigns" element={<RecetteCampaignsPage />} />
          <Route path="/verdicts" element={<VerdictsPage />} />
          <Route path="/rag" element={<RagPage />} />
          <Route path="/discovery" element={<DiscoveryPage />} />
          <Route path="/detect" element={<DetectPage />} />
          <Route path="/registry" element={<RegistryPage />} />
          <Route path="/probe" element={<ProbePage />} />
          <Route path="/corpus" element={<CorpusPage />} />
          <Route path="/sim" element={<SimPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/ai-backends" element={<AiBackendsPage />} />
          <Route path="/servers" element={<ServersPage />} />
          <Route path="/control" element={<ControlPage />} />
          <Route path="/metrics" element={<MetricsPage />} />
          <Route path="/catalog" element={<CatalogPage />} />
          <Route path="/approvals" element={<ApprovalsPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/observability" element={<ObservabilityPage />} />
          <Route path="/proxy" element={<ProxyPage />} />
        </Routes>
      </main>
    </div>
  );
}
