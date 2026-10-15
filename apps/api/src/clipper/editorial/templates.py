from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from clipper.captions import caption_config_for_preset
from clipper.domain.editing_plan import (
    CaptionPreset,
    EditingPlanV1,
    Effect,
    EffectType,
    EnhancementLevel,
    TransitionStyle,
    VideoTemplate,
)


@dataclass(frozen=True)
class TemplateStyle:
    caption_preset: CaptionPreset
    caption_style: Literal["clean", "kinetic_highlight", "karaoke"]
    frame_style: Literal["blurred_background", "center_crop"]
    enhancement_level: EnhancementLevel
    transition_style: TransitionStyle
    render_hook: bool
    render_cta: bool
    motion: Literal["punch_zoom", "slow_zoom"] | None = None
    progress_bar: bool = False


_TEMPLATES = {
    VideoTemplate.CLEAN_FOCUS: TemplateStyle(
        CaptionPreset.CLEAN,
        "clean",
        "blurred_background",
        EnhancementLevel.CLEAN,
        TransitionStyle.CUT,
        False,
        False,
    ),
    VideoTemplate.BOLD_VIRAL: TemplateStyle(
        CaptionPreset.BOLD_VIRAL,
        "kinetic_highlight",
        "center_crop",
        EnhancementLevel.AGGRESSIVE,
        TransitionStyle.CUT,
        True,
        True,
        motion="punch_zoom",
        progress_bar=True,
    ),
    VideoTemplate.PODCAST: TemplateStyle(
        CaptionPreset.PODCAST,
        "kinetic_highlight",
        "blurred_background",
        EnhancementLevel.DYNAMIC,
        TransitionStyle.CUT,
        True,
        True,
        motion="slow_zoom",
    ),
    VideoTemplate.STORY: TemplateStyle(
        CaptionPreset.KARAOKE,
        "karaoke",
        "blurred_background",
        EnhancementLevel.DYNAMIC,
        TransitionStyle.FADE,
        True,
        True,
        motion="slow_zoom",
        progress_bar=True,
    ),
}

_MANAGED_EFFECTS = {
    EffectType.PUNCH_ZOOM,
    EffectType.SLOW_ZOOM,
    EffectType.PROGRESS_BAR,
}


def apply_video_template(plan: EditingPlanV1, template: VideoTemplate) -> EditingPlanV1:
    """Apply a deterministic social-video look while preserving editorial content."""

    if template is VideoTemplate.CUSTOM:
        return plan.model_copy(update={"video_template": template})

    style = _TEMPLATES[template]
    caption_config = caption_config_for_preset(style.caption_preset)
    caption_payload = caption_config.model_dump(mode="json")
    for field in (
        "highlighted_words",
        "text_override",
        "source_language",
        "target_language",
        "translation_mode",
        "translated_text",
    ):
        caption_payload[field] = getattr(plan.caption_config, field)

    effects = [effect for effect in plan.effects if effect.type not in _MANAGED_EFFECTS]
    duration = plan.timeline_duration
    if style.motion == "punch_zoom":
        effects.append(
            Effect(
                time_seconds=min(1, duration / 4),
                type=EffectType.PUNCH_ZOOM,
                parameters={"scale": 1.16, "duration_seconds": 0.7},
            )
        )
    elif style.motion == "slow_zoom":
        effects.append(
            Effect(
                time_seconds=min(2, duration / 4),
                type=EffectType.SLOW_ZOOM,
                parameters={"scale": 1.08, "duration_seconds": min(5, duration)},
            )
        )
    if style.progress_bar:
        effects.append(Effect(time_seconds=0, type=EffectType.PROGRESS_BAR))

    payload = plan.model_dump(mode="json")
    payload.update(
        {
            "video_template": template,
            "caption_config": caption_payload,
            "caption_style": style.caption_style,
            "frame_style": style.frame_style,
            "enhancement_level": style.enhancement_level,
            "transition_style": style.transition_style,
            "hook": (
                plan.hook.model_copy(update={"render": style.render_hook}).model_dump(mode="json")
                if plan.hook
                else None
            ),
            "cta": (
                plan.cta.model_copy(update={"render": style.render_cta}).model_dump(mode="json")
                if plan.cta
                else None
            ),
            "effects": [effect.model_dump(mode="json") for effect in effects],
        }
    )
    return EditingPlanV1.model_validate(payload)
