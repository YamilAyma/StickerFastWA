import io
from pathlib import Path
import sys
import zipfile

import cv2
from fastapi.testclient import TestClient
from PIL import Image
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.app import create_app
from server import background
from logic.animation import clip_bounds, encode_frames, validate_sticker
from .test_server import picture, wait_for_job


def gif():
    output = io.BytesIO()
    frames = [Image.new("RGBA", (80, 40), color) for color in ("red", "blue")]
    frames[0].save(
        output,
        "GIF",
        save_all=True,
        append_images=frames[1:],
        duration=[500, 500],
        loop=0,
    )
    return output.getvalue()


def video(tmp_path, seconds=3):
    path = tmp_path / "source.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 12, (80, 64))
    assert writer.isOpened()
    for index in range(round(seconds * 12)):
        frame = np.zeros((64, 80, 3), dtype=np.uint8)
        frame[:] = (0, 0, 255) if index < 12 else (255, 0, index % 5 * 20)
        writer.write(frame)
    writer.release()
    return path.read_bytes()


def test_video_trim_and_player_frames(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        upload = client.post(
            "/api/animations", files={"file": ("source.avi", video(tmp_path))}
        )
        assert upload.status_code == 201, upload.text
        source = upload.json()
        assert (
            source["duration"] == 3
            and source["min_seconds"] == 1
            and source["max_seconds"] == 10
        )
        base = f'/api/animations/{source["id"]}'
        assert client.get(base + "/frame?t=1").status_code == 200
        assert client.get(base + "/frame?t=3").status_code == 422
        assert (
            client.post(base + "/render", json={"start": 0, "end": 0.5}).status_code
            == 422
        )
        assert (
            client.post(base + "/render", json={"start": 2, "end": 4}).status_code
            == 422
        )
        result = client.post(
            base + "/render", json={"start": 1, "end": 2, "crop_mode": "center_crop"}
        )
        assert result.status_code == 200, result.text
        data = result.json()
        assert data["valid"] and data["duration_ms"] == 1000 and data["frames"] > 1
        assert (data["width"], data["height"]) == (512, 512) and data["bytes"] <= 500000
        png = client.get(data["url"] + "/frame/0")
        with Image.open(io.BytesIO(png.content)) as frame:
            pixel = frame.getpixel((256, 256))
            assert pixel[2] > 200 and pixel[0] < 100
        assert client.get(data["url"] + "/frame/9999").status_code == 404
        assert client.delete(base).status_code == 204
        assert client.get(data["url"]).status_code == 404


def test_video_shorter_than_one_second_rejected(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert (
            client.post(
                "/api/animations", files={"file": ("short.avi", video(tmp_path, 0.5))}
            ).status_code
            == 422
        )
        response = client.post(
            "/api/animations", files={"file": ("short.avi", video(tmp_path, 1.5))}
        )
        assert response.status_code == 201
        result = client.post(
            f'/api/animations/{response.json()["id"]}/render',
            json={"start": 0.25, "end": 1.25},
        )
        assert result.status_code == 200 and result.json()["duration_ms"] == 1000


def test_animation_text_fonts_geometry_and_background(tmp_path, monkeypatch):
    calls = []

    def segment(image):
        calls.append(1)
        result = image.copy()
        result.putalpha(Image.new("L", image.size, 128))
        return result

    monkeypatch.setattr(background, "segment", segment)
    with TestClient(create_app(tmp_path)) as client:
        source = client.post(
            "/api/animations", files={"file": ("source.gif", gif())}
        ).json()
        base = f'/api/animations/{source["id"]}'
        result = client.post(
            base + "/render",
            json={
                "end": 1,
                "remove_bg": True,
                "text": "Hola Perú",
                "font": "lobster",
                "rotate": 90,
                "flip": True,
                "zoom": 0.75,
                "x": 20,
            },
        )
        assert result.status_code == 200, result.text
        data = result.json()
        assert len(calls) == 2 and data["frames"] == 2
        assert data["durations"] == [500, 500] and data["valid"]
        content = client.get(data["url"]).content
        with Image.open(io.BytesIO(content)) as image:
            for index in range(2):
                image.seek(index)
                image.load()
                assert image.getchannel("A").getextrema() == (0, 255)
        job_response = client.post(
            "/api/jobs",
            data={"name": "Exact render", "author": "Test"},
            files={"files": ("ready.webp", content)},
        )
        job = wait_for_job(client, job_response.json()["id"])
        assert job["status"] == "completed"
        with zipfile.ZipFile(
            io.BytesIO(client.get(job["download_url"]).content)
        ) as archive:
            name = next(name for name in archive.namelist() if name.endswith(".webp"))
            assert archive.read(name) == content
        assert (
            client.post(base + "/render", json={"font": "../../anything"}).status_code
            == 422
        )
        assert client.post(base + "/render", json={"zoom": 5}).status_code == 422
        assert (
            client.post(base + "/render", json={"text_color": "bad"}).status_code == 422
        )


def test_mixed_collection_default_and_strict_mode(tmp_path):
    files = [("files", ("image.png", picture())), ("files", ("motion.gif", gif()))]
    with TestClient(create_app(tmp_path)) as client:
        response = client.post(
            "/api/jobs", data={"name": "Mixed", "author": "Test"}, files=files
        )
        assert response.status_code == 202, response.text
        job = wait_for_job(client, response.json()["id"])
        assert job["status"] == "completed"
        assert any("mixto" in message for message in job["warnings"])
        manifest = client.get(job["preview_url"]).json()["stickers"]
        assert [s["frames"] for s in manifest] == [1, 2]
        assert all(s["validation"]["valid"] for s in manifest)
        assert (
            client.post(
                "/api/jobs",
                data={"name": "Strict", "author": "Test", "strict_whatsapp": "true"},
                files=files,
            ).status_code
            == 422
        )
        files = files * 3
        response = client.post(
            "/api/jobs",
            data={"name": "Strict", "author": "Test", "strict_whatsapp": "true"},
            files=files,
        )
        job = wait_for_job(client, response.json()["id"])
        assert job["status"] == "completed" and len(job["packs"]) == 2
        stickers = client.get(job["preview_url"]).json()["stickers"]
        assert [s["frames"] for s in stickers] == [1, 1, 1, 2, 2, 2]
        assert not job["warnings"]


def test_strict_encoder_keeps_size_timing_and_limits(tmp_path):
    output = tmp_path / "result.webp"
    frames = [Image.new("RGBA", (512, 512), color) for color in ("red", "blue")]
    encode_frames(frames, [300, 700], output)
    report = validate_sticker(output)
    assert (
        report["valid"]
        and report["duration_ms"] == 1000
        and (report["width"], report["height"]) == (512, 512)
    )
    with pytest.raises(ValueError):
        clip_bounds({"animated": True, "video": True, "duration": 20}, 0, 10.1)
    with pytest.raises(ValueError):
        clip_bounds({"animated": True, "video": True, "duration": 20}, float("nan"), 2)


def test_maximum_clip_and_long_source(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        source = client.post(
            "/api/animations", files={"file": ("long.avi", video(tmp_path, 12))}
        ).json()
        base = f'/api/animations/{source["id"]}'
        assert source["duration"] == 12
        assert (
            client.post(base + "/render", json={"start": 1, "end": 11.01}).status_code
            == 422
        )
        response = client.post(base + "/render", json={"start": 1, "end": 11})
        assert response.status_code == 200, response.text
        assert response.json()["duration_ms"] == 10000 and response.json()["valid"]


def test_strict_mode_rebalances_small_last_pack(tmp_path):
    files = [("files", (f"{index}.png", picture())) for index in range(31)]
    with TestClient(create_app(tmp_path)) as client:
        response = client.post(
            "/api/jobs",
            data={"name": "Balanced", "author": "Test", "strict_whatsapp": "true"},
            files=files,
        )
        job = wait_for_job(client, response.json()["id"])
        assert job["status"] == "completed"
        assert [pack["total"] for pack in job["packs"]] == [28, 3]
        assert not job["warnings"]


def test_failed_background_render_can_retry(tmp_path, monkeypatch):
    def fail(frame):
        raise RuntimeError("Model unavailable")

    monkeypatch.setattr(background, "segment", fail)
    with TestClient(create_app(tmp_path)) as client:
        source = client.post("/api/animations", files={"file": ("a.gif", gif())}).json()
        base = f'/api/animations/{source["id"]}'
        assert (
            client.post(base + "/render", json={"remove_bg": True}).status_code == 503
        )
        assert client.post(base + "/render", json={}).status_code == 200


def test_high_fps_gif_is_bounded_before_decoding(tmp_path):
    from logic.animation import media_info, read_clip

    path = tmp_path / "fast.gif"
    frames = [Image.new("RGB", (8, 8), (index * 2, 17, 50)) for index in range(121)]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=10)
    info = media_info(path)
    output, durations = read_clip(path, info, 0, info["duration"])
    try:
        assert len(output) == 120
        assert sum(durations) == 1210
        assert min(durations) >= 8
    finally:
        for image in output:
            image.close()


def test_default_already_homogeneous_parts_have_no_mixed_warning(tmp_path):
    files = [("files", (f"{index}.png", picture())) for index in range(30)]
    files += [("files", (f"{index}.gif", gif())) for index in range(3)]
    with TestClient(create_app(tmp_path)) as client:
        response = client.post(
            "/api/jobs", data={"name": "Compatible", "author": "Test"}, files=files
        )
        job = wait_for_job(client, response.json()["id"])
        assert job["status"] == "completed"
        assert [pack["total"] for pack in job["packs"]] == [30, 3]
        assert not job["warnings"]
