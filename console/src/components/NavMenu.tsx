import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

import ProxyNavBadge from "./ProxyNavBadge";

/**
 * Grouped top navigation. The console exposes ~30 pages; a flat link bar wraps
 * into an unreadable wall for the web-only researcher. Pages are grouped into a
 * handful of dropdowns (discover -> judge -> govern -> observe), so the bar shows
 * a few group buttons and reveals the pages on demand. Pure navigation: no API
 * call, so no response-envelope contract to honour (R16 is about API-calling
 * components).
 */

interface NavItem {
  to: string;
  label: string;
  /** Only the proxy link carries a live status badge. */
  badge?: "proxy";
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

/** Standalone link shown before the groups (the researcher's home). */
const HOME: NavItem = { to: "/dashboard", label: "Tableau de bord" };

/** Group order = researcher mental model: discover, judge, manage, inspect runs,
 * govern, observe. Labels are kept identical to the previous flat bar so muscle
 * memory survives the regroup. */
const NAV_GROUPS: NavGroup[] = [
  {
    label: "Discovery",
    items: [
      { to: "/discovery", label: "Discovery" },
      { to: "/discovery-exchange", label: "Discovery x Echange" },
      { to: "/discovery-overview", label: "Discovery overview" },
      { to: "/detect", label: "Reperage" },
      { to: "/probe", label: "Probe" },
    ],
  },
  {
    label: "Recette",
    items: [
      { to: "/recette", label: "Recette" },
      { to: "/campaigns", label: "Campagnes" },
      { to: "/recette-campaigns", label: "Campagnes recette" },
      { to: "/verdicts", label: "Verdicts" },
      { to: "/rag", label: "RAG" },
      { to: "/sim", label: "Red-team" },
    ],
  },
  {
    label: "Agents",
    items: [
      { to: "/agents", label: "Agents" },
      { to: "/agent-registry", label: "Registry" },
      { to: "/registry", label: "Catalogue" },
      { to: "/ai-backends", label: "IA" },
      { to: "/ia-prompts", label: "Prompts IA" },
      { to: "/servers", label: "Serveurs" },
    ],
  },
  {
    label: "Runs & flux",
    items: [
      { to: "/runs", label: "Runs" },
      { to: "/flux", label: "Flux" },
      { to: "/live", label: "Temps reel" },
    ],
  },
  {
    label: "Gouvernance",
    items: [
      { to: "/control", label: "Control" },
      { to: "/catalog", label: "Catalog" },
      { to: "/approvals", label: "Approvals" },
      { to: "/audit", label: "Audit" },
    ],
  },
  {
    label: "Observabilite",
    items: [
      { to: "/observability", label: "Observabilite" },
      { to: "/metrics", label: "Metriques" },
      { to: "/graph", label: "Graphe" },
      { to: "/proxy", label: "Proxy", badge: "proxy" },
      { to: "/receipts", label: "Receipts" },
    ],
  },
];

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "nav-link nav-link-active" : "nav-link";
}

function NavItemLink({ item, onNavigate }: { item: NavItem; onNavigate: () => void }): JSX.Element {
  return (
    <NavLink to={item.to} className={navLinkClass} onClick={onNavigate}>
      {item.label}
      {item.badge === "proxy" ? <ProxyNavBadge /> : null}
    </NavLink>
  );
}

export default function NavMenu(): JSX.Element {
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const navRef = useRef<HTMLElement | null>(null);
  const location = useLocation();

  // Close the open dropdown on any click outside the nav and on Escape.
  useEffect(() => {
    function onPointerDown(event: MouseEvent): void {
      if (navRef.current && !navRef.current.contains(event.target as Node)) {
        setOpenGroup(null);
      }
    }
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        setOpenGroup(null);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  const closeMenu = (): void => setOpenGroup(null);

  return (
    <nav className="app-nav" ref={navRef}>
      <NavLink to={HOME.to} className={navLinkClass}>
        {HOME.label}
      </NavLink>
      {NAV_GROUPS.map((group) => {
        const isOpen = openGroup === group.label;
        const hasActiveChild = group.items.some((item) => item.to === location.pathname);
        const buttonClass = [
          "nav-group-button",
          isOpen ? "nav-group-button-open" : "",
          hasActiveChild ? "nav-group-button-active" : "",
        ]
          .filter(Boolean)
          .join(" ");
        return (
          <div key={group.label} className="nav-group">
            <button
              type="button"
              className={buttonClass}
              aria-haspopup="true"
              aria-expanded={isOpen}
              onClick={() => setOpenGroup(isOpen ? null : group.label)}
            >
              {group.label}
              <span className="nav-group-caret" aria-hidden="true">
                {isOpen ? "▴" : "▾"}
              </span>
            </button>
            {isOpen ? (
              <div className="nav-dropdown" role="menu">
                {group.items.map((item) => (
                  <NavItemLink key={item.to} item={item} onNavigate={closeMenu} />
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </nav>
  );
}
