from collections.abc import Callable

from clipper.domain.editing_plan import EditingPlanV1, VideoTemplate
from clipper.editorial import apply_video_template


def test_bold_viral_template_applies_a_complete_look_and_preserves_caption_content(
    make_plan: Callable[..., EditingPlanV1],
) -> None:
    payload = make_plan().model_dump(mode="json")
    payload["caption_config"].update(
        {
            "text_override": "Corrected transcript",
            "target_language": "de",
            "translation_mode": "translated",
            "translated_text": "Korrigiertes Transkript",
        }
    )
    payload["effects"] = [
        {"time_seconds": 2, "type": "sound_effect", "parameters": {"volume_db": -20}}
    ]

    templated = apply_video_template(
        EditingPlanV1.model_validate(payload), VideoTemplate.BOLD_VIRAL
    )

    assert templated.video_template == "bold_viral"
    assert templated.caption_config.preset == "bold_viral"
    assert templated.caption_config.text_override == "Corrected transcript"
    assert templated.caption_config.translated_text == "Korrigiertes Transkript"
    assert templated.frame_style == "center_crop"
    assert templated.hook and templated.hook.render is True
    assert {effect.type for effect in templated.effects} == {
        "sound_effect",
        "punch_zoom",
        "progress_bar",
    }


def test_switching_templates_replaces_only_template_managed_effects(
    make_plan: Callable[..., EditingPlanV1],
) -> None:
    viral = apply_video_template(make_plan(), VideoTemplate.BOLD_VIRAL)

    clean = apply_video_template(viral, VideoTemplate.CLEAN_FOCUS)

    assert clean.video_template == "clean_focus"
    assert clean.caption_config.preset == "clean"
    assert clean.effects == []
    assert clean.hook and clean.hook.render is False
