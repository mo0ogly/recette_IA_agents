/**
 * Small nav pill showing whether proxy debug tracing is ON or OFF.
 *
 * Polls GET /proxy/debug so an operator sees at a glance whether the proxy
 * console will record anything (parametrable via AGENTRAIL_PROXY_DEBUG, R5). A
 * fetch failure hides the pill rather than crashing the header.
 */

import { useEffect, useState } from "react";

import { getProxyDebugStatus } from "../api/client";

const POLL_INTERVAL_MS = 5000;

export default function ProxyNavBadge(): JSX.Element | null {
  const [enabled, setEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = (): void => {
      getProxyDebugStatus()
        .then((s) => {
          if (alive) {
            setEnabled(s.debug_enabled);
          }
        })
        .catch(() => {
          if (alive) {
            setEnabled(null);
          }
        });
    };
    tick();
    const timer = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  if (enabled === null) {
    return null;
  }
  return (
    <span
      className="proxy-nav-badge"
      data-enabled={enabled}
      title={
        enabled
          ? "Proxy debug tracing actif"
          : "Proxy debug tracing inactif (AGENTRAIL_PROXY_DEBUG)"
      }
    >
      debug {enabled ? "ON" : "OFF"}
    </span>
  );
}
