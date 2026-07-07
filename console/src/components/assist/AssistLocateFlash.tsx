/**
 * "Localiser dans l'UI" effect: when the URL carries ?assist-locate=<loc>,
 * flash the element tagged data-assist-loc=<loc> (an AI button or the dock).
 * Mounted once next to the dock in App.tsx; renders nothing.
 */

import { useEffect } from "react";
import { useLocation } from "react-router-dom";

export default function AssistLocateFlash(): null {
  const location = useLocation();

  useEffect(() => {
    const loc = new URLSearchParams(location.search).get("assist-locate");
    if (loc === null) {
      return;
    }
    // Let the target page render its buttons before querying.
    const timer = window.setTimeout(() => {
      const target = document.querySelector(`[data-assist-loc="${CSS.escape(loc)}"]`);
      if (target instanceof HTMLElement) {
        target.scrollIntoView({ block: "center" });
        target.classList.add("assist-locate-flash");
        window.setTimeout(() => target.classList.remove("assist-locate-flash"), 3000);
      }
    }, 300);
    return () => window.clearTimeout(timer);
  }, [location]);

  return null;
}
