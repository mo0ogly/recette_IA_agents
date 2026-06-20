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

import { Suspense, useCallback, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import PageHelp from "../../components/help/PageHelp";
import LaunchPanel from "./LaunchPanel";
import type { SourceId, SourceStatus } from "./proxyMenu";
import SourceMenu from "./SourceMenu";
import { SOURCE_DESCRIPTORS } from "./sources";
import useProxyCounts from "./useProxyCounts";
import "./proxy.css";

/** The registered source ids, for validating the ?source= query param. */
const VALID_SOURCES = new Set<SourceId>(SOURCE_DESCRIPTORS.map((s) => s.id));

export default function ProxyPage(): JSX.Element {
  // Active source is derived from the URL (?source=wire), not duplicated into
  // state: it makes a view deep-linkable and keeps back/forward in sync. An
  // unknown or missing value falls back to the default (first) source.
  const [searchParams, setSearchParams] = useSearchParams();
  const rawSource = searchParams.get("source");
  const source: SourceId =
    rawSource !== null && VALID_SOURCES.has(rawSource as SourceId)
      ? (rawSource as SourceId)
      : SOURCE_DESCRIPTORS[0].id;

  const onSelectSource = useCallback(
    (id: SourceId): void => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("source", id);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const [statusById, setStatusById] = useState<Partial<Record<SourceId, SourceStatus>>>({});

  // Background poll of the lightweight status endpoints fills a badge for EVERY
  // source, even ones whose panel is closed. The mounted (active) panel reports
  // a fresher, strict-aware value through onStatus, so it wins for that source.
  const backgroundCounts = useProxyCounts();
  const menuStatus = useMemo<Partial<Record<SourceId, SourceStatus>>>(() => {
    const merged = { ...backgroundCounts };
    const activeStatus = statusById[source];
    if (activeStatus !== undefined) {
      merged[source] = activeStatus;
    }
    return merged;
  }, [backgroundCounts, statusById, source]);

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

      <LaunchPanel
        onLaunched={(runId) =>
          setSearchParams(
            (prev) => {
              const next = new URLSearchParams(prev);
              next.set("source", "sessions");
              next.set("run", runId);
              return next;
            },
            { replace: true },
          )
        }
      />

      <SourceMenu
        sources={SOURCE_DESCRIPTORS}
        active={source}
        onSelect={onSelectSource}
        statusById={menuStatus}
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
