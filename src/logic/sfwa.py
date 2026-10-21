"""Backward-compatible desktop facade over the shared processing engine."""
from pathlib import Path

from .desktop import DesktopIntegration
from .engine import StickerEngine


class Sfwa(DesktopIntegration, StickerEngine):
    def __init__(self, source_dir=None, preferences_path=None):
        super().__init__(source_dir=source_dir)
        self.preferences_path = Path(preferences_path).resolve() if preferences_path is not None else self.source_dir / "data" / "user.json"
