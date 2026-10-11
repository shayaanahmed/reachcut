# Troubleshooting

- **Doctor reports missing FFmpeg:** install a current FFmpeg build that includes ffprobe and the `subtitles` filter.
- **Python 3.14 native dependency errors:** use the pinned Python 3.12 environment via `uv python install 3.12` and `uv sync --python 3.12`.
- **Ollama connection failure:** start Ollama locally, pull the configured Qwen model, and verify its loopback URL.
- **Transcription runs out of memory:** choose `cpu_low_memory`, Whisper `small`, INT8, and disable optional diarization/VLM stages.
- **A failed job after restart:** inspect the stage error in the project API and retry; successful stages with matching cache keys are reused.
- **Rendering fails:** confirm the FFmpeg build exposes libx264 (or configure a detected hardware encoder) and the subtitle file is readable.
- **Docker API cannot reach Ollama on macOS:** keep Ollama running natively and use the base `compose.yaml`; do not add the Ollama override. Verify `curl http://localhost:11434/api/version` on the host.
- **The Ollama container has no model:** run the model setup command from `docs/docker.md`; model downloads are intentionally not automatic during normal startup.
- **Next.js reports that `/api/projects/upload` exceeded 10 MB:** rebuild the current web image. Uploads now use `CLIPPER_BROWSER_API_URL` to bypass Next's buffering rewrite proxy and stream directly to FastAPI.
- **Editorial selection reports malformed candidates:** rebuild the API, then choose **Retry analysis**. Completed probe and transcription stages are cached; structured output is retried, and candidates with unsafe timestamps are discarded individually.
- **Meta returns no Facebook Pages:** set the Facebook Login for Business Configuration ID in `CLIPPER_INSTAGRAM_LOGIN_CONFIG_ID` (or `CLIPPER_FACEBOOK_LOGIN_CONFIG_ID`) and include the required Page permissions and assets in that configuration. Also grant `business_management` when the Page belongs to a Meta Business Portfolio; Meta can otherwise return an empty `/me/accounts` list despite granting `pages_show_list`. ReachCut checks `/me/permissions` after an empty Page response and names missing permissions. An app administrator role still does not grant Page access: give the same Facebook user direct Facebook access under **Page settings → Page setup → Page access**. If ReachCut was previously authorized, remove it under **Facebook settings → Business integrations**, restart ReachCut, select **Reconnect**, and select the Page in Meta's consent screen.
