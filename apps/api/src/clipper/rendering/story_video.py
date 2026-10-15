from __future__ import annotations

import json
import subprocess
import textwrap
from collections.abc import Callable
from pathlib import Path

from clipper.generation import StoryPlan
from clipper.media import MediaError, require_tool
from clipper.media.video_validation import valid_generated_video

ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]


class StoryVideoFinisher:
    """Deterministic FFmpeg finishing for locally generated scene clips."""

    def __init__(
        self,
        runner: ProcessRunner = subprocess.run,
        tool_locator: Callable[[str], str] = require_tool,
    ) -> None:
        self._runner = runner
        self._tool_locator = tool_locator

    def validate_video(self, video: Path, duration: float | None = None) -> bool:
        return valid_generated_video(
            video, duration, runner=self._runner, tool_locator=self._tool_locator
        )

    def valid_frame(self, frame: Path) -> bool:
        if not frame.is_file() or not frame.stat().st_size:
            return False
        result = self._runner(
            [
                self._tool_locator("ffmpeg"),
                "-v",
                "error",
                "-nostdin",
                "-xerror",
                "-i",
                str(frame),
                "-frames:v",
                "1",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        return result.returncode == 0

    def extract_last_frame(self, video: Path, output: Path) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True)
        pending = output.with_name(f"{output.stem}.pending{output.suffix}")
        command = [
            self._tool_locator("ffmpeg"),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-sseof",
            "-0.08",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(pending),
        ]
        self._run(command, "extract the scene continuity frame")
        if not pending.is_file() or not pending.stat().st_size:
            raise MediaError("The scene continuity frame was not produced")
        pending.replace(output)
        return output

    def stitch(self, scenes: list[Path], output: Path, *, plan: StoryPlan | None = None) -> Path:
        if not scenes:
            raise MediaError("No generated scenes are available to finish")
        output.parent.mkdir(parents=True, exist_ok=True)
        pending = output.with_name(f"{output.stem}.pending{output.suffix}")
        executable = self._tool_locator("ffmpeg")
        command = [executable, "-hide_banner", "-nostdin", "-y"]
        for scene in scenes:
            command.extend(["-i", str(scene)])
        if plan and len(plan.scenes) != len(scenes):
            raise MediaError("Scene files do not match the storyboard")
        dimensions: tuple[int, int] | None = None
        if plan and any(scene.crop for scene in plan.scenes):
            probe = self._runner(
                [
                    self._tool_locator("ffprobe"),
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height",
                    "-of",
                    "json",
                    str(scenes[0]),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            try:
                stream = json.loads(probe.stdout)["streams"][0]
                dimensions = (int(stream["width"]), int(stream["height"]))
            except (ValueError, KeyError, TypeError, IndexError) as error:
                raise MediaError("Could not read the output framing dimensions") from error
        filters: list[str] = []
        for index in range(len(scenes)):
            scene_plan = plan.scenes[index] if plan else None
            duration = scene_plan.output_duration_seconds if scene_plan else None
            start = scene_plan.trim_start_seconds if scene_plan else 0
            end = (
                (scene_plan.trim_end_seconds or scene_plan.duration_seconds) if scene_plan else None
            )
            speed = scene_plan.playback_speed if scene_plan else 1
            trim = f"trim=start={start}:end={end}," if end else ""
            audio_trim = f"atrim=start={start}:end={end}," if end else ""
            tempo = f",atempo={speed}" if speed != 1 else ""
            fades = (
                f",afade=t=in:d=0.04,afade=t=out:st={duration - 0.04}:d=0.04" if duration else ""
            )
            framing = ""
            if scene_plan and scene_plan.crop and dimensions:
                crop = scene_plan.crop
                framing = (
                    f"crop=w=trunc(iw*{crop.width}/2)*2:h=trunc(ih*{crop.height}/2)*2:"
                    f"x=trunc(iw*{crop.x}/2)*2:y=trunc(ih*{crop.y}/2)*2,"
                    f"scale={dimensions[0]}:{dimensions[1]},"
                )
            filters.append(
                f"[{index}:v:0]{trim}{framing}setpts=(PTS-STARTPTS)/{speed},setsar=1,fps=24[v{index}]"
            )
            filters.append(f"[{index}:a:0]{audio_trim}asetpts=PTS-STARTPTS{tempo}{fades}[a{index}]")
        inputs = "".join(f"[v{index}][a{index}]" for index in range(len(scenes)))
        filters.append(f"{inputs}concat=n={len(scenes)}:v=1:a=1[vcat][a]")
        captions: list[str] = []
        if plan:
            for name, text, start, end, position in (
                ("hook", plan.hook_caption, 0, 2.7, "h*0.10"),
                (
                    "ending",
                    plan.end_caption,
                    max(0, plan.output_duration_seconds - 3),
                    plan.output_duration_seconds,
                    "h*0.76",
                ),
            ):
                if not text:
                    continue
                caption = output.parent / f"{name}-caption.txt"
                caption.write_text(textwrap.fill(text, width=24), encoding="utf-8")
                path = str(caption).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
                captions.append(
                    f"drawtext=font='Noto Sans':textfile='{path}':expansion=none:"
                    "fontcolor=white:fontsize=h/26:box=1:boxcolor=black@0.5:boxborderw=12:"
                    f"x=(w-text_w)/2:y={position}:enable='between(t,{start},{end})'"
                )
        filters.append("[vcat]" + (",".join(captions) if captions else "null") + "[v]")
        filter_graph = ";".join(filters)
        command.extend(
            [
                "-filter_complex",
                filter_graph,
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                "16",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(pending),
            ]
        )
        self._run(command, "finish the story video")
        if not self.validate_video(pending):
            raise MediaError("The finished story video is incomplete or invalid")
        pending.replace(output)
        return output

    def _run(self, command: list[str], action: str) -> None:
        result = self._runner(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=7_200,
        )
        if result.returncode != 0:
            raise MediaError(f"Could not {action}: {result.stderr[-1_500:]}")
