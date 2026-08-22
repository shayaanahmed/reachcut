# ADR 0003: Explicit local providers, no silent cloud or heuristic production fallback

Status: accepted

The default transcription provider is faster-whisper and the default editorial provider is an Ollama-hosted Qwen model. Missing models produce actionable stage failures. Lightweight deterministic implementations exist only as injected test doubles. This preserves privacy expectations and prevents degraded output from masquerading as AI analysis.

