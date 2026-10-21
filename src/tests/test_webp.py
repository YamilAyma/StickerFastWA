"""Exercise animated WebP conversion with real temporary input files."""
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logic.engine import StickerEngine


def test_transform_webp(tmp_path, monkeypatch):
    source = tmp_path / "source"
    output = tmp_path / "output"
    source.mkdir()
    output.mkdir()
    frames = [Image.new("RGBA", (80, 60), color) for color in ("red", "blue", "green")]
    frames[0].save(source / "animated.webp", save_all=True, append_images=frames[1:], duration=80, loop=0)
    monkeypatch.chdir(tmp_path)
    StickerEngine().transform_webp("animated.webp", str(source), str(output), "sticker.webp")
    with Image.open(output / "sticker.webp") as result:
        assert result.format == "WEBP"
        assert result.size == (512, 512)
        assert result.n_frames >= 3
    assert sorted(p.name for p in output.iterdir()) == ["sticker.webp"]
    assert sorted(p.name for p in source.iterdir()) == ["animated.webp"]
