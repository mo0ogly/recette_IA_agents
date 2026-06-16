"""In-process agent capture (the hook surface).

The interception MECHANISM is adapted from cyberark/agentwatch (Apache-2.0); the
enriched-trace FIELD SET is adapted from tensorstax/agenttrace (MIT). Both are
re-homed into this project's existing seams -- the ``LlmBackend`` wrapper idiom
(``recette/llm_cache.py::CachingLlm``), the surface recording
(``recette/surface/recording.py``), and the proxy trace recorder
(``recette/platform/proxy/tracing.py``) -- rather than copied as a parallel tool.

A captured run feeds two existing consumers, in sync:
- DETECTION: tool-call intents become ``hook_sdk`` observations in a
  ``CaptureRecording`` -> the same deterministic surface judge (I4).
- ENRICHMENT: each LLM call becomes an ``LlmCallTrace`` carrying operational
  metrics (tokens, latency) -- wall-clock latency is ops-only and never enters
  the decision/judge path (cf. ``maf-standard.md``).

See NOTICE and docs/plans/2026-06-16-agent-capture-multisurface-design.md.
"""
