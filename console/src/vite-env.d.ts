/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the inspect_ia_agents platform API. Falls back to http://localhost:8090 (canonical port) when unset. */
  readonly VITE_INSPECT_IA_AGENTS_API_URL?: string;
}
