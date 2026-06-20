/**
 * sources -- the declarative source registry of the Proxy console.
 *
 * The single place that enumerates the READ-ONLY views over the governed
 * side-effect boundary (I5). The orchestrator (`index.tsx`) renders the menu
 * and the active panel straight from this list, with NO per-source branch:
 * adding a new view is one entry here (its id, label, one-line hint, and the
 * panel component). This is what makes the console evolutive.
 *
 * `app` is the default view, so its panel is imported statically (no code-split
 * benefit, and it keeps the first paint -- and the contract test -- synchronous).
 * The optional overlays (`wire`, `reconcile`) are lazy: their panels load only
 * when their tab is opened, behind a Suspense boundary in the orchestrator.
 */

import { lazy } from "react";

import AppTracesPanel from "./AppTracesPanel";
import type { SourceDescriptor } from "./proxyMenu";

const WirePanel = lazy(() => import("./WirePanel"));
const ReconcilePanel = lazy(() => import("./ReconcilePanel"));
const SessionsPanel = lazy(() => import("./SessionsPanel"));

/**
 * The ordered source registry. Order is the menu order. The first entry is the
 * default active source.
 */
export const SOURCE_DESCRIPTORS: readonly SourceDescriptor[] = [
  {
    id: "app",
    label: "traces app",
    hint: "effets de bord applicatifs (intention + reponse, I5)",
    Component: AppTracesPanel,
  },
  {
    id: "wire",
    label: "wire (mitmproxy)",
    hint: "octets reseau de l'echange agent -> cible",
    Component: WirePanel,
  },
  {
    id: "reconcile",
    label: "reconciliation",
    hint: "join wire <-> audit : detecte un chemin non-medie",
    Component: ReconcilePanel,
  },
  {
    id: "sessions",
    label: "sessions",
    hint: "echanges agent<->serveur groupes par session (run/agent/target)",
    Component: SessionsPanel,
  },
] as const;
