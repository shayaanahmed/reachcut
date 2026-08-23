# Local model configuration

Models are not downloaded during application startup.

For the balanced profile, install Ollama and run `ollama pull qwen3:8b-q4_K_M`, then set `CLIPPER_EDITORIAL_MODEL`. The multilingual transcription default is `large-v3-turbo` with INT8 on CPU. Set `CLIPPER_WHISPER_MODEL=small` on low-memory systems. Prepare the configured Docker model explicitly with `pnpm docker:whisper-model`; the weights are stored in the persistent `whisper-models` volume.

If transcription reports that it cannot locate files on the Hub or find a local snapshot, Docker DNS was unavailable while the selected model was missing from the cache. Confirm connectivity and rerun `pnpm docker:whisper-model` before retrying analysis.

Ollama is the initial editorial adapter. The provider protocol is compatible with future llama.cpp, MLX, vLLM, and controlled Transformers adapters without changing pipeline services. VLM and diarization are optional and disabled until configured because their memory and licensing needs differ.

Model output is treated as untrusted: it must be JSON, match the candidate schema, quote transcript evidence, and pass timestamp and plan validation. Model identifiers and quantization settings are recorded in provenance.
