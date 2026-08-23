from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptionLanguage:
    code: str | None
    initial_prompt: str | None = None


def language_settings(code: str | None) -> TranscriptionLanguage:
    """Return language-specific transcription hints in one owned module."""

    if code == "ur":
        return TranscriptionLanguage(
            code="ur",
            # Intentional native Urdu punctuation.
            initial_prompt="یہ ایک اردو گفتگو ہے۔ درست اردو رسم الخط اور اوقاف استعمال کریں۔",  # noqa: RUF001
        )
    return TranscriptionLanguage(code=code)
