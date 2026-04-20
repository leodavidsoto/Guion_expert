"""Schemas Pydantic para outputs tipados del LLM (Master Stack cinematográfico).

Se cargan via Anthropic tool use, no via regex de free-text.
"""
from .cinematic import (
    CameraPhysics,
    MotionIntent,
    PostProduction,
    SonicAtmosphere,
    VeoPrompt,
    VisualAnchor,
    choose_video_model,
    VIDEO_MODEL_ROUTING,
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
]
