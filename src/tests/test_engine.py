"""Regression checks for using the engine outside a desktop process."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import zipfile

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logic.engine import StickerEngine
from logic.sfwa import Sfwa


def create_job(directory, package):
    directory.mkdir()
    icon = directory / "icon.png"
    Image.new("RGB", (120, 80), "red").save(icon)
    events = []
    result = StickerEngine().create_pack({
        "package": package, "animated": False, "namepack": package,
        "author": "Local test", "directory": str(directory), "icon": str(icon),
        "conserve": True,
    }, progress_callback=lambda current, total: events.append((current, total)))
    assert result
    assert events
    extension = "wemojipack" if package == "wemoji" else "wastickers"
    with zipfile.ZipFile(directory / f"{package}.{extension}") as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        stickers = [name for name in names if name.endswith(".webp")]
        assert stickers
        for name in stickers:
            with archive.open(name) as entry, Image.open(entry) as image:
                assert image.size == (512, 512)
        if package == "wemoji":
            metadata = next(name for name in names if name.endswith(".wspdata"))
            assert json.loads(archive.read(metadata))["b"] == package
        else:
            assert archive.read("title.txt").decode() == package
            assert archive.read("author.txt").decode() == "Local test"
    assert icon.exists()
    assert not any(p.is_dir() for p in directory.iterdir())


def test_parallel_jobs_do_not_change_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = os.getcwd()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(create_job, tmp_path / package, package)
                   for package in ("wemoji", "stickerMaker")]
        for future in futures:
            future.result()
    assert os.getcwd() == before


def test_failed_job_cleans_staging_and_preserves_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert StickerEngine().create_pack({
        "package": "stickerMaker", "animated": False, "namepack": "invalid",
        "author": "Test", "directory": str(tmp_path),
        "icon": str(tmp_path / "missing.png"), "conserve": True,
    }) is False
    assert os.getcwd() == str(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_desktop_preferences_are_instance_local(tmp_path):
    preferences = tmp_path / "preferences.json"
    desktop = Sfwa(preferences_path=preferences)
    desktop.set_user_preferences({"lang": "es", "theme": "dark", "directory": str(tmp_path)})
    other = Sfwa(source_dir=tmp_path / "other", preferences_path=tmp_path / "other.json")
    other.cancel_processing()
    assert not desktop.cancel_flag
    assert desktop.get_user_preferences()["directory"] == str(tmp_path)
    assert desktop.get_language_json("es")
