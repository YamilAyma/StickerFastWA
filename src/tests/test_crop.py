"""Verify actual framing, transparency, and timing across supported media."""
import hashlib
from pathlib import Path
import sys

from PIL import Image, ImageDraw
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logic.engine import StickerEngine


def wide_image():
    image = Image.new('RGBA', (200, 100), 'red')
    ImageDraw.Draw(image).rectangle((50, 0, 149, 99), fill='lime')
    return image


@pytest.mark.parametrize('extension', ['png', 'jpg', 'webp'])
@pytest.mark.parametrize('mode', ['center_crop', 'fit'])
def test_static_framing_without_source_changes(tmp_path, extension, mode):
    source = tmp_path / 'input'
    output = tmp_path / 'output'
    source.mkdir()
    output.mkdir()
    original = source / f'wide.{extension}'
    image = wide_image().convert('RGB')
    image.save(original)
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    StickerEngine().process_images(str(source), str(output), crop_mode=mode)
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before
    with Image.open(next(output.glob('*.webp'))) as result:
        assert result.size == (512, 512)
        if mode == 'fit':
            assert result.getpixel((256, 30))[3] == 0
            assert result.getpixel((40, 256))[0] > 200
        else:
            assert result.getpixel((256, 30))[3] == 255
            assert result.getpixel((40, 256))[1] > 200


@pytest.mark.parametrize('mode', ['center_crop', 'fit'])
def test_source_alpha_preserved(mode):
    image = wide_image()
    ImageDraw.Draw(image).rectangle((80, 30, 120, 70), fill=(0, 0, 0, 0))
    before = image.tobytes()
    with StickerEngine().transform_image_obj(image, crop_mode=mode) as result:
        assert result.getpixel((256, 256))[3] == 0
    assert image.tobytes() == before


@pytest.mark.parametrize('extension', ['gif', 'webp'])
@pytest.mark.parametrize('mode', ['center_crop', 'fit'])
def test_animated_framing_and_timing(tmp_path, extension, mode):
    source = tmp_path / f'input.{extension}'
    frames = [wide_image(), wide_image()]
    ImageDraw.Draw(frames[1]).rectangle((60, 0, 139, 99), fill='blue')
    frames[0].save(source, save_all=True, append_images=frames[1:], duration=[80, 160], loop=0)
    output = tmp_path / 'output.webp'
    StickerEngine().transform_gif(str(source), str(tmp_path), output.name, crop_mode=mode)
    with Image.open(output) as result:
        assert result.n_frames == 2
        for index, expected_duration in enumerate((80, 160)):
            result.seek(index)
            result.load()
            assert result.info['duration'] == expected_duration
            assert result.getpixel((256, 30))[3] == (0 if mode == 'fit' else 255)
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([source.name, output.name])


def test_static_gif_and_non_media_files(tmp_path):
    source = tmp_path / 'input'
    output = tmp_path / 'output'
    source.mkdir()
    output.mkdir()
    wide_image().save(source / 'single.gif')
    (source / 'notes.txt').write_text('not a sticker')
    updates = []
    StickerEngine().process_images(str(source), str(output), progress_callback=lambda *args: updates.append(args))
    assert len(list(output.glob('*.webp'))) == 1
    assert updates == [(1, 1)]


@pytest.mark.parametrize('mode', ['center_crop', 'fit'])
def test_video_uses_the_same_framing(tmp_path, mode):
    import cv2
    import numpy as np
    source = tmp_path / 'wide.avi'
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'MJPG'), 12, (200, 100))
    assert writer.isOpened()
    for index in range(4):
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        frame[:] = (0, 0, 255)
        frame[:, 50:150] = (index * 20, 255, 0)
        writer.write(frame)
    writer.release()
    assert StickerEngine().process_video_file(str(source), str(tmp_path), 'result.webp', crop_mode=mode)
    with Image.open(tmp_path / 'result.webp') as result:
        assert result.n_frames > 1
        assert result.getpixel((256, 30))[3] == (0 if mode == 'fit' else 255)
