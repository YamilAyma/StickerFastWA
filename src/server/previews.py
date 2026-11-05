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
                issues = []
                frames = getattr(image, 'n_frames', 1)
                for frame in range(frames):
                    image.seek(frame)
                    image.load()
                    delay=image.info.get('duration',0)
                    duration += delay if frames>1 else 0
                    if frames>1 and delay<8:issues.append('Los cuadros deben durar al menos 8 ms.')
                if image.size!=(512,512):issues.append('Las dimensiones deben ser 512 × 512.')
                if len(content)>(500000 if frames>1 else 100000):issues.append('El sticker supera el peso permitido.')
                if duration>10000:issues.append('La animación supera los 10 segundos.')
                stickers.append(dict(index=len(stickers), width=image.width,
                                     height=image.height, bytes=len(content),
                                     frames=frames, duration_ms=duration, validation=dict(valid=not issues, issues=list(dict.fromkeys(issues)))))
    return stickers


def read_sticker(archive_path: Path, index: int) -> bytes:
    with zipfile.ZipFile(archive_path) as archive:
        entries = [entry for entry in archive.infolist() if entry.filename.endswith('.webp')]
        if index < 0 or index >= len(entries):
            raise IndexError(index)
        return archive.read(entries[index])
