"""Extractors package — subsistemas de extracción biométrica."""
from capture.extractors.kinematic import KinematicExtractor
from capture.extractors.facial import FacialExtractor
from capture.extractors.acoustic import AcousticExtractor

__all__ = ["KinematicExtractor", "FacialExtractor", "AcousticExtractor"]
