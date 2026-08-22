from pydantic import BaseModel, ConfigDict, Field


class Word(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    probability: float | None = Field(default=None, ge=0, le=1)
    speaker: str | None = None


class Segment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    text: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    words: list[Word]


class Transcript(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: str
    language_probability: float | None = Field(default=None, ge=0, le=1)
    segments: list[Segment]
    provider: str
    model: str
