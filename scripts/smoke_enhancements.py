"""Exercise the production enhancement filter graph against the generated fixture."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from clipper.captions import phrase_cues, serialize_ass
from clipper.domain.editing_plan import EditingPlanV1
from clipper.domain.transcript import Word
from clipper.rendering import RenderRequest, VideoRenderer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    bin_dir = args.output.parent / "enhancement-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    link = bin_dir / "ffmpeg"
    link.unlink(missing_ok=True)
    link.symlink_to(args.ffmpeg.resolve())
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"

    plan = EditingPlanV1.model_validate(
        {
            "source": {"start_seconds": 0, "end_seconds": 7},
            "source_slices": [
                {"start_seconds": 0, "end_seconds": 3},
                {"start_seconds": 4, "end_seconds": 7},
            ],
            "content_mode": "gameplay",
            "enhancement_level": "aggressive",
            "scores": {
                "overall": 80,
                "hook": 80,
                "clarity": 80,
                "payoff": 80,
                "visual_interest": 80,
            },
            "rationale": "Enhancement smoke fixture.",
            "hook": {
                "text": "Can every layer render?",
                "start_seconds": 0,
                "end_seconds": 2,
                "render": True,
            },
            "caption_style": "kinetic_highlight",
            "caption_config": {"preset": "gaming", "animation": "pop"},
            "frame_style": "center_crop",
            "tracking": {
                "enabled": True,
                "strategy": "action",
                "keyframes": [
                    {"time_seconds": 0, "center_x": 0.35, "center_y": 0.5},
                    {"time_seconds": 3, "center_x": 0.65, "center_y": 0.5},
                    {"time_seconds": 6, "center_x": 0.5, "center_y": 0.5},
                ],
            },
            "transition_style": "fade",
            "transition_duration_seconds": 0.15,
            "secondary_media": [
                {
                    "asset_id": "game",
                    "filename": "game.mp4",
                    "kind": "gameplay",
                    "loop": True,
                    "placement": "bottom",
                },
                {
                    "asset_id": "broll",
                    "filename": "broll.mp4",
                    "kind": "broll",
                    "start_seconds": 2,
                    "end_seconds": 3.5,
                    "placement": "fullscreen",
                },
                {
                    "asset_id": "reaction",
                    "filename": "reaction.mp4",
                    "kind": "reaction",
                    "start_seconds": 3.5,
                    "end_seconds": 5.5,
                    "placement": "pip",
                },
                {
                    "asset_id": "music",
                    "filename": "music.mp4",
                    "kind": "music",
                    "muted": False,
                    "loop": True,
                    "volume_db": -24,
                    "placement": "audio",
                },
            ],
            "effects": [
                {
                    "time_seconds": 1,
                    "type": "punch_zoom",
                    "parameters": {"scale": 1.12, "duration_seconds": 0.5},
                },
                {"time_seconds": 0, "type": "progress_bar", "parameters": {}},
                {
                    "time_seconds": 2,
                    "type": "question_card",
                    "parameters": {"text": "All effects?", "duration_seconds": 1},
                },
            ],
            "cta": {
                "text": "Follow for the next test",
                "start_seconds": 4.5,
                "end_seconds": 6,
                "render": True,
                "style": "follow",
            },
        }
    )
    subtitles = args.output.with_suffix(".ass")
    words = [
        Word(text="Enhancement", start_seconds=0, end_seconds=1),
        Word(text="render", start_seconds=1, end_seconds=2),
        Word(text="verified", start_seconds=2, end_seconds=3),
    ]
    subtitles.write_text(
        serialize_ass(
            phrase_cues(words),
            plan.caption_config,
            hook=plan.hook,
            cta=plan.cta,
            effects=plan.effects,
        ),
        encoding="utf-8",
    )
    assets = {asset.asset_id: args.source for asset in plan.secondary_media}
    VideoRenderer().render(
        RenderRequest(
            args.source, plan, subtitles, args.output, preview=True, asset_paths=assets
        )
    )
    if not args.output.is_file() or args.output.stat().st_size < 10_000:
        raise RuntimeError("enhancement render output missing or unexpectedly small")
    print(f"verified enhancements {args.output} ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
