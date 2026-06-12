/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the AgentRail platform API. Falls back to http://localhost:8080 when unset. */
  readonly VITE_AGENTRAIL_API_URL?: string;
}
