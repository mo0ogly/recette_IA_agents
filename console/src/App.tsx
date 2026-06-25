import { Navigate, Route, Routes } from "react-router-dom";

import AgentsPage from "./pages/agents";
import AiBackendsPage from "./pages/ai-backends";
import ApprovalsPage from "./pages/approvals";
import AuditPage from "./pages/audit";
import AgentRegistryPage from "./pages/agent-registry";
import CatalogPage from "./pages/catalog";
import ReceiptsPage from "./pages/receipts";
import ControlPage from "./pages/control";
import GraphPage from "./pages/graph";
import MetricsPage from "./pages/metrics";
import CampaignsPage from "./pages/campaigns";
import CorpusPage from "./pages/corpus";
import SimPage from "./pages/sim";
import DashboardPage from "./pages/dashboard";
import DetectPage from "./pages/detect";
import DiscoveryPage from "./pages/discovery";
import DiscoveryExchangePage from "./pages/discovery-exchange";
import DiscoveryOverviewPage from "./pages/discovery-overview";
import FluxPage from "./pages/flux";
import LivePage from "./pages/live";
import ObservabilityPage from "./pages/observability";
import ProbePage from "./pages/probe";
import RunsExplorerPage from "./pages/runs";
import NavMenu from "./components/NavMenu";
import ProxyPage from "./pages/proxy";
import RagPage from "./pages/rag";
import RecettePage from "./pages/recette";
import RegistryPage from "./pages/registry";
import RecetteCampaignsPage from "./pages/recette-campaigns";
import ServersPage from "./pages/servers";
import VerdictsPage from "./pages/verdicts";

export default function App(): JSX.Element {
  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="app-title">inspect_ia_agents</span>
        <NavMenu />
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
          <Route path="/discovery-exchange" element={<DiscoveryExchangePage />} />
          <Route path="/discovery-overview" element={<DiscoveryOverviewPage />} />
          <Route path="/detect" element={<DetectPage />} />
          <Route path="/registry" element={<RegistryPage />} />
          <Route path="/agent-registry" element={<AgentRegistryPage />} />
          <Route path="/probe" element={<ProbePage />} />
          <Route path="/runs" element={<RunsExplorerPage />} />
          <Route path="/corpus" element={<CorpusPage />} />
          <Route path="/sim" element={<SimPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/ai-backends" element={<AiBackendsPage />} />
          <Route path="/servers" element={<ServersPage />} />
          <Route path="/control" element={<ControlPage />} />
          <Route path="/metrics" element={<MetricsPage />} />
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/catalog" element={<CatalogPage />} />
          <Route path="/approvals" element={<ApprovalsPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/observability" element={<ObservabilityPage />} />
          <Route path="/proxy" element={<ProxyPage />} />
          <Route path="/receipts" element={<ReceiptsPage />} />
        </Routes>
      </main>
    </div>
  );
}
