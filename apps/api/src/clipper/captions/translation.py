from typing import Protocol


class CaptionTranslationProvider(Protocol):
    """Port for translating display text without changing transcript timing."""

    @property
    def identity(self) -> str: ...

    def translate(self, text: str, source_language: str | None, target_language: str) -> str: ...
