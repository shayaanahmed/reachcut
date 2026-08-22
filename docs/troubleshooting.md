# Troubleshooting

- **Doctor reports missing FFmpeg:** install a current FFmpeg build that includes ffprobe and the `subtitles` filter.
- **Python 3.14 native dependency errors:** use the pinned Python 3.12 environment via `uv python install 3.12` and `uv sync --python 3.12`.
- **Ollama connection failure:** start Ollama locally, pull the configured Qwen model, and verify its loopback URL.
- **Transcription runs out of memory:** choose `cpu_low_memory`, Whisper `small`, INT8, and disable optional diarization/VLM stages.
- **A failed job after restart:** inspect the stage error in the project API and retry; successful stages with matching cache keys are reused.
- **Rendering fails:** confirm the FFmpeg build exposes libx264 (or configure a detected hardware encoder) and the subtitle file is readable.

