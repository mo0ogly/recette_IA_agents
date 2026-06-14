/**
 * ProxySelector -- pick the transport route agent side effects take (direct vs
 * the mitmproxy wire overlay). Shared by the network-debug consoles (the /proxy
 * wire panel and the per-run network log).
 *
 * Transport only: switching the route changes how a side effect reaches its
 * target, never the decision (allow/deny/escalate) or the recorded action log
 * (I4). The selection applies to runs started after it; in-flight runs keep
 * their route. The backend holds the active choice (GET/POST /proxy/route), so
 * every console that mounts this selector reflects the same state.
 */

import { useCallback, useEffect, useState } from "react";

import { getProxyRoute, setProxyRoute } from "../api/client";
import type { ProxyRouteTarget } from "../types/platform";

export default function ProxySelector(): JSX.Element {
  const [targets, setTargets] = useState<ProxyRouteTarget[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (): Promise<void> => {
    try {
      const res = await getProxyRoute();
      setTargets(res.targets);
      setActive(res.active);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onSelect = useCallback(async (id: string): Promise<void> => {
    try {
      const res = await setProxyRoute(id);
      setActive(res.active);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  return (
    <div className="proxy-selector" role="group" aria-label="proxy route" data-testid="proxy-selector">
      <span className="proxy-selector-label">Proxy :</span>
      {targets.map((t) => (
        <button
          key={t.id}
          type="button"
          className="proxy-mode-btn"
          data-active={t.id === active}
          title={t.proxy_url ?? "direct (sans proxy)"}
          onClick={() => void onSelect(t.id)}
        >
          {t.label}
        </button>
      ))}
      {error !== null && <span className="proxy-selector-error">{error}</span>}
    </div>
  );
}
