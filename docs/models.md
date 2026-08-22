# Local model configuration

Models are not downloaded during application startup.

For the balanced profile, install Ollama and run `ollama pull qwen3:8b-q4_K_M`, then set `CLIPPER_EDITORIAL_MODEL`. The low-memory transcription default is `small` with INT8 on CPU. Set `CLIPPER_WHISPER_MODEL=medium` or `large-v3-turbo` when memory permits; faster-whisper downloads the chosen model on its first explicit processing run.

Ollama is the initial editorial adapter. The provider protocol is compatible with future llama.cpp, MLX, vLLM, and controlled Transformers adapters without changing pipeline services. VLM and diarization are optional and disabled until configured because their memory and licensing needs differ.

Model output is treated as untrusted: it must be JSON, match the candidate schema, quote transcript evidence, and pass timestamp and plan validation. Model identifiers and quantization settings are recorded in provenance.

