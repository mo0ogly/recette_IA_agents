import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import AgentsPage from "./pages/agents";
import ApprovalsPage from "./pages/approvals";
import AuditPage from "./pages/audit";
import CatalogPage from "./pages/catalog";

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "nav-link nav-link-active" : "nav-link";
}

export default function App(): JSX.Element {
  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="app-title">AgentRail Console</span>
        <nav className="app-nav">
          <NavLink to="/agents" className={navLinkClass}>
            Agents
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
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Navigate to="/agents" replace />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/catalog" element={<CatalogPage />} />
          <Route path="/approvals" element={<ApprovalsPage />} />
          <Route path="/audit" element={<AuditPage />} />
        </Routes>
      </main>
    </div>
  );
}
