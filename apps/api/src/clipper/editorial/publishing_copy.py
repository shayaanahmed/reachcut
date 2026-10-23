"""Consistent hashtag handling for pipeline drafts and publisher previews."""

import re

from clipper.editorial.growth import GrowthCreative

TAG = re.compile(r"(?<!\w)#[^\s#]{1,39}(?![^\s#])")


def hashtags(text: str) -> list[str]:
    return list(dict.fromkeys(match.group().rstrip(".,!?:;") for match in TAG.finditer(text)))


def caption_with_tags(caption: str, tags: list[str]) -> str:
    existing = {tag.casefold() for tag in hashtags(caption)}
    additions = list(dict.fromkeys(tag for tag in tags if tag.casefold() not in existing))
    return "\n\n".join(filter(None, [caption.strip(), " ".join(additions)]))


def complete_hashtags(creative: GrowthCreative, fallback: list[str]) -> GrowthCreative:
    packages = []
    for package in creative.packages:
        tags = package.hashtags or hashtags(package.caption) or fallback[:5]
        packages.append(package.model_copy(update={"hashtags": tags[:5]}))
    return creative.model_copy(update={"packages": packages})
