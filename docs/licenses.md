# Dependency, model, and asset licenses

Application source licensing must be chosen before public distribution. Third-party packages retain their own licenses; the lockfiles are the authoritative dependency inventory. Run `uv run pip-licenses` or an equivalent SBOM tool and `pnpm licenses list` before a release, and retain notices required by binary FFmpeg builds.

Model weights are not distributed by this repository. Users must review the license and acceptable-use terms for every downloaded Whisper, Qwen, Gemma, diarization, embedding, or vision checkpoint. A model's availability through a local runtime does not grant rights to its inputs or outputs.

No production music, fonts, sound effects, icons, or B-roll are bundled. Every future asset record must include identifier, source, license, attribution text, checksum, and allowed uses. The generated media fixture is CC0 as described in `fixtures/README.md`.

The development-only `ffmpeg-static`/`ffprobe-static` packages make fixture verification reproducible when a host binary is absent; production diagnostics still require an explicitly installed FFmpeg/ffprobe and deployments must comply with the selected build's LGPL/GPL configuration.
