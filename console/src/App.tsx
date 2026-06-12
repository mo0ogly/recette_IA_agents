import { NavLink, Navigate, Route, Routes } from "react-router-dom";

// Placeholder pages: real implementations arrive in Phase 2.

function AgentsPage(): JSX.Element {
  return <h1>Agents</h1>;
}

function CatalogPage(): JSX.Element {
  return <h1>Catalog</h1>;
}

function ApprovalsPage(): JSX.Element {
  return <h1>Approvals</h1>;
}

function AuditPage(): JSX.Element {
  return <h1>Audit</h1>;
}

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
