/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the inspect_ia_agents platform API. Falls back to http://localhost:8090 (canonical port) when unset. */
  readonly VITE_INSPECT_IA_AGENTS_API_URL?: string;
  /** Base URL of the local LiteLLM gateway (openai_compat preset). Falls back to http://localhost:4000 when unset. */
  readonly VITE_LLM_PROXY_URL?: string;
}
