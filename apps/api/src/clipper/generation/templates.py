from dataclasses import dataclass

from clipper.generation.contracts import VideoTemplateId


@dataclass(frozen=True)
class VideoTemplateDefinition:
    id: VideoTemplateId
    name: str
    description: str
    category: str
    prompt_hint: str
    style_prompt: str
    palette: tuple[str, str, str]
    badge: str


VIDEO_TEMPLATES: tuple[VideoTemplateDefinition, ...] = (
    VideoTemplateDefinition(
        "cinematic_story",
        "Cinematic story",
        "Live-action characters, expressive close-ups and filmic camera work.",
        "Realistic",
        "Write the story, characters and ending. ReachCut will direct it into shots.",
        "cinematic live-action film, natural skin texture, anamorphic depth, motivated lighting",
        ("0B1021", "6D43FF", "E9D5FF"),
        "CINEMA",
    ),
    VideoTemplateDefinition(
        "animated_adventure",
        "Animated adventure",
        "Expressive characters in a polished family-animation world.",
        "Animation",
        "Describe the hero, their goal, the obstacle and the emotional payoff.",
        "premium stylized animated feature, expressive faces, appealing shapes, "
        "rich color scripting",
        ("10233F", "2EC4B6", "FFF3B0"),
        "ADVENTURE",
    ),
    VideoTemplateDefinition(
        "anime_story",
        "Anime story",
        "Dynamic framing, graphic silhouettes and emotional anime pacing.",
        "Animation",
        "Describe the protagonist, power or conflict and the final visual beat.",
        "high-end cinematic anime, hand-painted backgrounds, controlled linework, "
        "dramatic compositing",
        ("21103B", "F044A7", "9DEBFF"),
        "ANIME",
    ),
    VideoTemplateDefinition(
        "stylized_3d",
        "Stylized 3D",
        "Tactile 3D characters with playful materials and deliberate art direction.",
        "Animation",
        "Describe the character design, miniature world and transformation or reveal.",
        "stylized 3D character film, tactile materials, global illumination, expressive animation",
        ("261506", "FF7A1A", "FFE6B7"),
        "3D STORY",
    ),
    VideoTemplateDefinition(
        "dark_mystery",
        "Dark mystery",
        "Suspenseful character storytelling with restrained reveals and atmosphere.",
        "Genre",
        "Describe what feels wrong, what the character discovers and the final twist.",
        "atmospheric mystery thriller, practical low-key light, subtle dread, "
        "grounded performances",
        ("07110C", "18A96B", "C8FFD9"),
        "MYSTERY",
    ),
    VideoTemplateDefinition(
        "documentary_realism",
        "Documentary realism",
        "Believable people and environments with intimate observational camera work.",
        "Realistic",
        "Describe a human moment with a clear place, action and emotional change.",
        "observational documentary realism, available light, authentic detail, handheld restraint",
        ("151515", "D0A85C", "F4ECDD"),
        "REAL LIFE",
    ),
)


def template_by_id(template_id: VideoTemplateId) -> VideoTemplateDefinition:
    return next(item for item in VIDEO_TEMPLATES if item.id == template_id)
