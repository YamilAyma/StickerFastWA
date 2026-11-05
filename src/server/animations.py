"""Temporary animation workbench, bounded to 10-second rendered clips."""

import io
import json
import math
from pathlib import Path
import shutil
from threading import Lock
import time
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, ConfigDict, field_validator
from PIL import Image
from logic.animation import media_info, clip_bounds, frame_at, render_media, FONT_ROOT
from server import background


class AnimationOptions(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    start: float = Field(default=0, ge=0)
    end: float | None = Field(default=None, gt=0)
    crop_mode: str = "fit"
    zoom: float = Field(default=1, ge=0.25, le=4)
    x: float = Field(default=0, ge=-512, le=512)
    y: float = Field(default=0, ge=-512, le=512)
    rotate: int = 0
    flip: bool = False
    text: str = Field(default="", max_length=120)
    font: str = "default"
    font_size: int = Field(default=40, ge=16, le=80)
    text_y: int = Field(default=432, ge=48, le=464)
    text_color: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    remove_bg: bool = False

    @field_validator("crop_mode")
    @classmethod
    def crop(cls, value):
        if value not in {"fit", "center_crop"}:
            raise ValueError("Invalid crop mode")
        return value

    @field_validator("rotate")
    @classmethod
    def rotation(cls, value):
        if value not in {0, 90, 180, 270}:
            raise ValueError("Invalid rotation")
        return value

    @field_validator("font")
    @classmethod
    def font_id(cls, value):
        fonts = {
            item["id"] for item in json.loads((FONT_ROOT / "catalog.json").read_text())
        }
        if value != "default" and value not in fonts:
            raise ValueError("Invalid font")
        return value


def animation_router(root):
    router = APIRouter(prefix="/api/animations")
    assets = {}
    lock = Lock()
    processing = Lock()

    def lookup(key):
        asset = assets.get(key)
        if not asset:
            raise HTTPException(404, "La sesión de edición ya no está disponible.")
        return asset

    @router.post("", status_code=201)
    def upload(file: UploadFile = File()):
        key = uuid.uuid4().hex
        with lock:
            for old, asset in list(assets.items()):
                if not asset["busy"] and time.monotonic() - asset["created"] > 1800:
                    shutil.rmtree(asset["directory"], ignore_errors=True)
                    del assets[old]
            if len(assets) >= 8:
                raise HTTPException(429, "Demasiadas sesiones de edición abiertas.")
            folder = root / ("animation-" + key)
            folder.mkdir()
            asset = dict(
                directory=folder, busy=True, created=time.monotonic(), results={}
            )
            assets[key] = asset
        try:
            suffix = Path(file.filename or "").suffix.lower()
            if suffix not in {".gif", ".webp", ".mp4", ".webm", ".mov", ".avi", ".mkv"}:
                raise ValueError("Formato de animación no admitido.")
            path = folder / ("source" + suffix)
            total = 0
            with path.open("wb") as output:
                while chunk := file.file.read(1024 * 1024):
                    total += len(chunk)
                    if total > 25 * 1024 * 1024:
                        raise HTTPException(413, "El archivo supera los 25 MB.")
                    output.write(chunk)
            info = media_info(path)
            if info["video"] and info["duration"] < 1 - 0.0001:
                raise ValueError("El video debe durar al menos 1 segundo.")

            with lock:
                asset.update(path=path, info=info, busy=False)
            times = []
            elapsed = 0
            for delay in info.get("durations", []):
                times.append(elapsed / 1000)
                elapsed += delay
            return dict(
                id=key,
                **{name: value for name, value in info.items() if name != "durations"},
                frame_times=times or None,
                max_seconds=10,
                min_seconds=1 if info["video"] else 0.008,
            )
        except Exception as error:
            with lock:
                assets.pop(key, None)
            shutil.rmtree(folder, ignore_errors=True)
            if isinstance(error, HTTPException):
                raise
            raise HTTPException(
                422,
                (
                    str(error)
                    if isinstance(error, ValueError)
                    else "No se pudo leer la animación."
                ),
            ) from error
        finally:
            file.file.close()

    @router.get("/{key}/frame")
    def source_frame(key: str, t: float = Query(default=0, ge=0, le=1800)):
        with lock:
            asset = lookup(key)
            if asset["busy"]:
                raise HTTPException(409, "La animación está ocupada.")
            if not math.isfinite(t) or (
                asset["info"]["animated"] and t >= asset["info"]["duration"]
            ):
                raise HTTPException(422, "Cuadro fuera de rango.")
            try:
                image = frame_at(asset["path"], t, asset["info"])
            except Exception as error:
                raise HTTPException(422, "No se pudo leer el cuadro.") from error
        image.thumbnail((768, 768))
        output = io.BytesIO()
        image.save(output, "PNG")
        image.close()
        return Response(
            output.getvalue(),
            media_type="image/png",
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/{key}/render")
    def render(key: str, options: AnimationOptions):
        if not processing.acquire(blocking=False):
            raise HTTPException(
                429,
                "Ya hay una animación en procesamiento. Inténtalo en unos segundos.",
            )
        background_locked = False
        asset = None
        activated = False
        destination = None
        committed = False
        try:
            with lock:
                asset = lookup(key)
                if asset["busy"]:
                    raise HTTPException(409, "La animación está ocupada.")
                clip_bounds(asset["info"], options.start, options.end)
                asset["busy"] = True
                activated = True
            if options.remove_bg:
                background_locked = background._lock.acquire(blocking=False)
                if not background_locked:
                    raise HTTPException(
                        429,
                        "Ya se está quitando otro fondo. Inténtalo en unos segundos.",
                    )
            result_id = uuid.uuid4().hex
            destination = asset["directory"] / (result_id + ".webp")
            report = render_media(
                asset["path"],
                destination,
                options.model_dump(),
                remove_background=background.segment if options.remove_bg else None,
            )
            with Image.open(destination) as image:
                durations = []
                for index in range(getattr(image, "n_frames", 1)):
                    image.seek(index)
                    image.load()
                    durations.append(image.info.get("duration", 0))
            with lock:
                while len(asset["results"]) >= 3:
                    old = next(iter(asset["results"]))
                    asset["results"].pop(old).unlink(missing_ok=True)
                asset["results"][result_id] = destination
                committed = True
            return dict(
                report,
                result_id=result_id,
                url=f"/api/animations/{key}/results/{result_id}",
                durations=durations,
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(
                503,
                "No se pudo procesar la animación. Comprueba el modelo si usas eliminación de fondo.",
            ) from error
        finally:
            if destination and not committed:
                destination.unlink(missing_ok=True)
            if asset and activated:
                with lock:
                    asset["busy"] = False
            if background_locked:
                background._lock.release()
            processing.release()

    @router.get("/{key}/results/{result_id}")
    def result_file(key: str, result_id: str):
        with lock:
            path = lookup(key)["results"].get(result_id)
            if not path:
                raise HTTPException(404, "Resultado no encontrado.")
            content = path.read_bytes()
        return Response(
            content, media_type="image/webp", headers={"Cache-Control": "no-store"}
        )

    @router.get("/{key}/results/{result_id}/frame/{index}")
    def result_frame(key: str, result_id: str, index: int):
        with lock:
            path = lookup(key)["results"].get(result_id)
            if not path:
                raise HTTPException(404, "Resultado no encontrado.")
            with Image.open(path) as image:
                if index < 0 or index >= getattr(image, "n_frames", 1):
                    raise HTTPException(404, "Cuadro fuera de rango.")
                image.seek(index)
                output = io.BytesIO()
                image.convert("RGBA").save(output, "PNG")
        return Response(
            output.getvalue(),
            media_type="image/png",
            headers={"Cache-Control": "no-store"},
        )

    @router.delete("/{key}", status_code=204)
    def delete(key: str):
        with lock:
            asset = assets.get(key)
            if asset and asset["busy"]:
                raise HTTPException(409, "La animación está ocupada.")
            if asset:
                assets.pop(key)
                shutil.rmtree(asset["directory"], ignore_errors=True)

    return router
