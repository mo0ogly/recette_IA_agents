/**
 * Proxy page -- debug console over the side-effect proxy traces (I5).
 *
 * Thin orchestrator over a declarative source registry (`SOURCE_DESCRIPTORS`):
 * it owns only the active-source selection and the per-source status map that
 * feeds the menu badges. Each view (application traces, wire overlay, wire<->
 * audit reconciliation) is a self-contained panel from the registry, rendered
 * behind a Suspense boundary; adding a new view is one registry entry, no branch
 * here. Read-only end to end (I1): every panel views effects that already
 * happened; this page never mutates one.
 */

import { Suspense, useMemo, useState } from "react";

import PageHelp from "../../components/help/PageHelp";
import type { SourceId, SourceStatus } from "./proxyMenu";
import SourceMenu from "./SourceMenu";
import { SOURCE_DESCRIPTORS } from "./sources";
import "./proxy.css";

export default function ProxyPage(): JSX.Element {
  const [source, setSource] = useState<SourceId>(SOURCE_DESCRIPTORS[0].id);
  const [statusById, setStatusById] = useState<Partial<Record<SourceId, SourceStatus>>>({});

  // One stable status setter per registered source, so a panel's polling
  // effect is not torn down and rebuilt on every orchestrator render.
  const onStatusById = useMemo(() => {
    const map = {} as Record<SourceId, (status: SourceStatus) => void>;
    for (const s of SOURCE_DESCRIPTORS) {
      map[s.id] = (status: SourceStatus) =>
        setStatusById((prev) => ({ ...prev, [s.id]: status }));
    }
    return map;
  }, []);

  const activeDescriptor =
    SOURCE_DESCRIPTORS.find((s) => s.id === source) ?? SOURCE_DESCRIPTORS[0];
  const ActivePanel = activeDescriptor.Component;

  return (
    <section className="proxy-page">
      <header className="proxy-header">
        <h1>Proxy</h1>
        <PageHelp topic="proxy" />
      </header>

      <SourceMenu
        sources={SOURCE_DESCRIPTORS}
        active={source}
        onSelect={setSource}
        statusById={statusById}
      />

      <Suspense
        fallback={
          <div className="proxy-viewer-msg">chargement {activeDescriptor.label}...</div>
        }
      >
        <ActivePanel onStatus={onStatusById[activeDescriptor.id]} />
      </Suspense>
    </section>
  );
}
