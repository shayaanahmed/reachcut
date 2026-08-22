# ADR 0001: Python local control plane with a separate TypeScript review client

Status: accepted

FastAPI owns pipeline and durable state; Next.js owns interaction and preview. Python has the strongest local transcription and vision ecosystem, while TypeScript supports Remotion and an accessible editor. A versioned JSON plan is the boundary. This adds two runtimes but prevents rendering from depending on unvalidated model prose.

