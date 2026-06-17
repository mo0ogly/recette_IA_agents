/**
 * proxyMenu -- the source-menu contract for the Proxy console.
 *
 * The Proxy page is a debug console over side-effect proxy traces (I5). It
 * surfaces several READ-ONLY views of the same governed boundary ("sources"):
 * the application-level trace list, the network-level wire overlay, and the
 * wire<->audit reconciliation. This module holds the small, pure contract that
 * makes that set of views EVOLUTIVE: a `SourceDescriptor` registry entry, the
 * status a mounted panel reports back up for its menu badge, and the pure
 * helper that classifies a badge. Adding a new source is one registry entry --
 * no orchestrator switch to touch.
 *
 * Pure + deterministic (I4): no clock, no I/O. The descriptor list itself lives
 * in `sources.tsx` (it references React components); only the types and the
 * badge classifier live here so they stay trivially unit-testable.
 */

import type { ComponentType } from "react";

/** The stable identifier of a Proxy source view. */
export type SourceId = "app" | "wire" | "reconcile";

/**
 * What a mounted source panel reports up to the menu for its live badge.
 *
 * `count` is the headline number for the view (traces, wire flows, bypass
 * flows). `failed` is the subset in a failure/alert state (drives the red
 * badge). `disabled` is true when the view's backend feature is off (e.g. the
 * wire overlay is not configured) -- the badge then reads "off", not "0", so an
 * unconfigured overlay is not mistaken for a quiet steady state.
 */
export interface SourceStatus {
  count: number;
  failed?: number;
  disabled?: boolean;
}

/** Props every source panel accepts. `onStatus` is optional: a panel that has
 *  nothing to report (or has not loaded yet) simply never calls it. */
export interface SourcePanelProps {
  onStatus?: (status: SourceStatus) => void;
}

/**
 * One entry of the source registry. `Component` is the panel rendered when the
 * source is active; it may be a lazy component (wrapped by the caller in a
 * Suspense boundary). `hint` is the one-line description shown under the label.
 */
export interface SourceDescriptor {
  id: SourceId;
  label: string;
  hint: string;
  Component: ComponentType<SourcePanelProps>;
}

/** The three badge states a menu entry can show. */
export type BadgeOutcome = "idle" | "ok" | "fail" | "off";

/**
 * Classify a source's reported status into a badge outcome. Pure.
 *
 * - no status yet            -> "idle" (panel not mounted / not loaded)
 * - feature disabled         -> "off"
 * - at least one failure      -> "fail"
 * - otherwise                 -> "ok"
 */
export function badgeOutcome(status: SourceStatus | undefined): BadgeOutcome {
  if (status === undefined) {
    return "idle";
  }
  if (status.disabled === true) {
    return "off";
  }
  if ((status.failed ?? 0) > 0) {
    return "fail";
  }
  return "ok";
}

/** The short text shown in a menu badge for a reported status. */
export function badgeLabel(status: SourceStatus | undefined): string {
  if (status === undefined) {
    return "";
  }
  if (status.disabled === true) {
    return "off";
  }
  const failed = status.failed ?? 0;
  return failed > 0 ? `${status.count} / ${failed} KO` : String(status.count);
}
