from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from clipper.domain.editing_plan import Hashtag


class PublishingMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    suggested_title: str = Field(min_length=1, max_length=100)
    suggested_description: str = Field(min_length=1, max_length=4000)
    hashtags: list[Hashtag] = Field(min_length=3, max_length=8)


class PublishingMetadataProvider(Protocol):
    @property
    def identity(self) -> str: ...

    def generate(self, title: str, transcript: str) -> PublishingMetadata: ...
