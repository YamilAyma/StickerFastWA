"""Inspect and serve the exact sticker bytes stored in a completed archive."""
from io import BytesIO
from pathlib import Path
import zipfile

from PIL import Image


def describe_stickers(archive_path: Path) -> list[dict]:
    stickers = []
    with zipfile.ZipFile(archive_path) as archive:
        for entry in archive.infolist():
            if not entry.filename.endswith('.webp'):
                continue
            content = archive.read(entry)
            with Image.open(BytesIO(content)) as image:
                duration = 0
                frames = getattr(image, 'n_frames', 1)
                for frame in range(frames):
                    image.seek(frame)
                    image.load()
                    duration += image.info.get('duration', 0) if frames > 1 else 0
                stickers.append(dict(index=len(stickers), width=image.width,
                                     height=image.height, bytes=len(content),
                                     frames=frames, duration_ms=duration))
    return stickers


def read_sticker(archive_path: Path, index: int) -> bytes:
    with zipfile.ZipFile(archive_path) as archive:
        entries = [entry for entry in archive.infolist() if entry.filename.endswith('.webp')]
        if index < 0 or index >= len(entries):
            raise IndexError(index)
        return archive.read(entries[index])
