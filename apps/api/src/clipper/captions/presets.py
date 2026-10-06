from clipper.domain.editing_plan import CaptionConfig, CaptionPreset, ContentMode


def caption_config_for_preset(preset: CaptionPreset) -> CaptionConfig:
    """Return a complete, deterministic caption configuration for a named preset."""

    common: dict[str, object] = {"preset": preset}
    variants: dict[CaptionPreset, dict[str, object]] = {
        CaptionPreset.CUSTOM: {},
        CaptionPreset.CLEAN: {
            "font_size": 54,
            "animation": "none",
            "highlight_color": "#D8FF42",
            "max_words_per_line": 6,
        },
        CaptionPreset.BOLD_VIRAL: {
            "font_size": 72,
            "animation": "pop",
            "highlight_color": "#FFD400",
            "outline_color": "#000000",
            "max_words_per_line": 4,
        },
        CaptionPreset.KARAOKE: {
            "font_size": 62,
            "animation": "karaoke",
            "highlight_color": "#42E8FF",
            "max_words_per_line": 5,
        },
        CaptionPreset.PODCAST: {
            "font_size": 56,
            "animation": "pop",
            "highlight_color": "#8BFFB0",
            "position": "bottom",
            "max_words_per_line": 6,
        },
        CaptionPreset.GAMING: {
            "font_size": 64,
            "animation": "pop",
            "highlight_color": "#FF4FD8",
            "position": "middle",
            "max_words_per_line": 4,
        },
        CaptionPreset.SPORTS: {
            "font_size": 68,
            "animation": "pop",
            "highlight_color": "#FFE14A",
            "position": "top",
            "max_words_per_line": 4,
        },
        CaptionPreset.MINIMAL: {
            "font_size": 46,
            "animation": "none",
            "highlight_color": "#FFFFFF",
            "outline_color": "#222222",
            "max_words_per_line": 7,
        },
        CaptionPreset.NEWS: {
            "font_size": 52,
            "animation": "none",
            "highlight_color": "#55B8FF",
            "position": "bottom",
            "max_words_per_line": 7,
        },
    }
    return CaptionConfig.model_validate({**common, **variants[preset]})


def caption_preset_for_mode(mode: ContentMode) -> CaptionPreset:
    """Choose a conservative default that matches the selected content mode."""

    return {
        ContentMode.PODCAST: CaptionPreset.PODCAST,
        ContentMode.GAMEPLAY: CaptionPreset.GAMING,
        ContentMode.SPORTS: CaptionPreset.SPORTS,
        ContentMode.NEWS: CaptionPreset.NEWS,
        ContentMode.TUTORIAL: CaptionPreset.CLEAN,
        ContentMode.PRODUCT: CaptionPreset.BOLD_VIRAL,
    }.get(mode, CaptionPreset.BOLD_VIRAL)
