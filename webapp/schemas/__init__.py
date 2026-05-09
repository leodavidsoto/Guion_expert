"""Schemas Pydantic para outputs tipados del LLM (Master Stack cinematográfico + Story Bible).

Se cargan via Anthropic tool use, no via regex de free-text.
"""
from .cinematic import (
    CameraPhysics,
    EditTransition,
    MotionIntent,
    PostProduction,
    SonicAtmosphere,
    VeoPrompt,
    VisualAnchor,
    choose_video_model,
    VIDEO_MODEL_ROUTING,
)
from .story_bible import (
    StoryBible,
    CharacterProfile,
    VisualDNA,
    SonicDNA,
    SAVE_THE_CAT_BEATS,
)

__all__ = [
    "CameraPhysics",
    "MotionIntent",
    "PostProduction",
    "SonicAtmosphere",
    "VeoPrompt",
    "VisualAnchor",
    "choose_video_model",
    "VIDEO_MODEL_ROUTING",
    # Edit Transitions (cinematografía algorítmica)
    "EditTransition",
    # Story Bible (M1)
    "StoryBible",
    "CharacterProfile",
    "VisualDNA",
    "SonicDNA",
    "SAVE_THE_CAT_BEATS",
]
