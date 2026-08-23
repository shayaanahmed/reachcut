from clipper.transcription import language_settings


def test_urdu_hint_is_kept_in_language_module() -> None:
    settings = language_settings("ur")

    assert settings.code == "ur"
    assert settings.initial_prompt is not None
    assert "اردو" in settings.initial_prompt


def test_other_languages_do_not_receive_urdu_prompt() -> None:
    assert language_settings("en").initial_prompt is None
    assert language_settings(None).code is None
