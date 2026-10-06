"""Render the generated CC0 fixture through the production media functions."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from clipper.domain.editing_plan import EditingPlanV1
from clipper.services.media import probe_media
from clipper.services.render import render_vertical


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--ffprobe", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--skip-probe",
        action="store_true",
        help="Skip the probe assertion when no native ffprobe binary is available.",
    )
    args = parser.parse_args()

    bin_dir = args.output.parent / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name, source in (("ffmpeg", args.ffmpeg), ("ffprobe", args.ffprobe)):
        link = bin_dir / name
        link.unlink(missing_ok=True)
        link.symlink_to(source.resolve())
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"

    if not args.skip_probe:
        media = probe_media(args.source, max_duration_seconds=60)
        assert 7.5 < float(str(media["duration_seconds"])) < 8.5
    subtitles = args.output.with_suffix(".srt")
    subtitles.write_text(
        "1\n00:00:00,000 --> 00:00:03,000\nGenerated fixture caption\n"
    )
    plan = EditingPlanV1.model_validate(
        {
            "source": {"start_seconds": 0, "end_seconds": 6},
            "scores": {
                "overall": 80,
                "hook": 80,
                "clarity": 80,
                "payoff": 80,
                "visual_interest": 80,
            },
            "rationale": "Programmatic render smoke fixture.",
            "hook": None,
            "caption_style": "clean",
            "emphasis": [],
            "effects": [],
            "cta": None,
        }
    )
    render_vertical(args.source, plan, subtitles, args.output, preview=True)
    if not args.output.is_file() or args.output.stat().st_size < 10_000:
        raise RuntimeError("render output missing or unexpectedly small")
    print(f"verified {args.output} ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
