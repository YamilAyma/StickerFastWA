"""Bounded media conversion shared by preview and package export."""

from pathlib import Path
import math
import json
from PIL import Image, ImageDraw, ImageFont

MAX_SECONDS = 10
MAX_FRAMES = 120
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv"}
FONT_ROOT = Path(__file__).resolve().parents[1] / "server" / "web" / "fonts"


def media_info(path):
    path = Path(path)
    if path.suffix.lower() in VIDEO_EXTENSIONS:
        import cv2

        cap = cv2.VideoCapture(str(path))
        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(
                cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            )
            if (
                not cap.isOpened()
                or not math.isfinite(fps)
                or fps <= 0
                or not math.isfinite(count)
                or count <= 0
            ):
                raise ValueError("No se pudo leer la duración del video.")
            duration = count / fps
            if width * height > 25_000_000 or duration > 1800:
                raise ValueError("El archivo supera los límites de procesamiento.")
            return dict(
                video=True,
                animated=True,
                width=width,
                height=height,
                frames=int(count),
                duration=duration,
                fps=fps,
            )
        finally:
            cap.release()
    with Image.open(path) as image:
        count = getattr(image, "n_frames", 1)
        if (
            image.width * image.height > 25_000_000
            or count * image.width * image.height > 250_000_000
            or count > 5000
        ):
            raise ValueError("El archivo supera los límites de procesamiento.")
        durations = []
        if count > 1:
            for index in range(count):
                image.seek(index)
                image.load()
                durations.append(max(8, int(image.info.get("duration", 80))))
        if sum(durations) > 1800000:
            raise ValueError("El archivo supera los límites de procesamiento.")
        return dict(
            video=False,
            animated=count > 1,
            width=image.width,
            height=image.height,
            frames=count,
            duration=sum(durations) / 1000,
            durations=durations,
            fps=count * 1000 / sum(durations) if durations else 0,
        )


def clip_bounds(info, start=0, end=None):
    if not info["animated"]:
        return 0, 0
    end = info["duration"] if end is None else end
    minimum = 1 if info["video"] else 0.008
    if (
        not all(math.isfinite(value) for value in (start, end))
        or start < 0
        or end > info["duration"] + 0.001
        or end <= start
    ):
        raise ValueError(
            "El inicio y el fin deben estar dentro de la duración del archivo."
        )
    if end - start < minimum - 0.0001:
        raise ValueError("El fragmento de video debe durar al menos 1 segundo.")
    if end - start > MAX_SECONDS + 0.0001:
        raise ValueError(
            "La animación puede durar como máximo 10 segundos. Elige un fragmento."
        )
    return start, min(end, info["duration"])


def frame_at(path, seconds, info=None):
    info = info or media_info(path)
    if info["video"]:
        import cv2

        cap = cv2.VideoCapture(str(path))
        try:
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0, seconds) * 1000)
            ok, frame = cap.read()
            if not ok:
                raise ValueError("No se pudo leer el cuadro.")
            return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert(
                "RGBA"
            )
        finally:
            cap.release()
    with Image.open(path) as image:
        elapsed = 0
        for index, duration in enumerate(info.get("durations", [])):
            if seconds * 1000 < elapsed + duration:
                image.seek(index)
                break
            elapsed += duration
        else:
            if info["animated"]:
                image.seek(info["frames"] - 1)
        frame = image.convert("RGBA")
        frame.thumbnail((1024, 1024))
        return frame


def read_clip(path, info, start, end, cancelled=lambda: False):
    frames, durations = [], []
    if info["video"]:
        import cv2

        cap = cv2.VideoCapture(str(path))
        count = min(MAX_FRAMES, max(1, math.ceil((end - start) * 12)))
        times = [round((end - start) * 1000 * i / count) for i in range(count + 1)]
        try:
            for index in range(count):
                if cancelled():
                    raise InterruptedError("Cancelled")
                cap.set(cv2.CAP_PROP_POS_MSEC, (start + times[index] / 1000) * 1000)
                ok, frame = cap.read()
                if not ok:
                    raise ValueError("No se pudo leer el cuadro.")
                image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert(
                    "RGBA"
                )
                image.thumbnail((768, 768))
                frames.append(image)
                durations.append(times[index + 1] - times[index])
        finally:
            cap.release()
    else:
        with Image.open(path) as image:
            if not info["animated"]:
                return [image.convert("RGBA")], [0]
            elapsed = 0
            for index, duration in enumerate(info["durations"]):
                if cancelled():
                    raise InterruptedError("Cancelled")
                left, right = max(elapsed, round(start * 1000)), min(
                    elapsed + duration, round(end * 1000)
                )
                if right > left:
                    image.seek(index)
                    frame = image.convert("RGBA")
                    frame.thumbnail((768, 768))
                    frames.append(frame)
                    durations.append(right - left)
                elapsed += duration
                if elapsed >= end * 1000:
                    break
    cleaned, timing, carry = [], [], 0
    for frame, delay in zip(frames, durations):
        if delay < 8 and not timing and carry + delay >= 8:
            cleaned.append(frame)
            timing.append(carry + delay)
            carry = 0
        elif delay < 8:
            if timing:
                timing[-1] += delay
            else:
                carry += delay
            frame.close()
        else:
            cleaned.append(frame)
            timing.append(delay + carry)
            carry = 0
    frames, durations = cleaned, timing
    if len(frames) > MAX_FRAMES:
        stride = math.ceil(len(frames) / MAX_FRAMES)
        keep = frames[::stride]
        for index, frame in enumerate(frames):
            if index % stride:
                frame.close()
        frames = keep
        durations = [
            sum(durations[index : index + stride])
            for index in range(0, len(durations), stride)
        ]
    return frames, durations


def encode_frames(frames, durations, destination):
    animated = len(frames) > 1
    limit = 500_000 if animated else 100_000
    for stride in ((1, 2, 3, 4) if animated else (1,)):
        selected = frames[::stride]
        timing = [
            sum(durations[index : index + stride])
            for index in range(0, len(durations), stride)
        ]
        for quality in (85, 65, 45, 25, 10):
            selected[0].save(
                destination,
                format="WEBP",
                save_all=animated,
                append_images=selected[1:] if animated else [],
                duration=timing if animated else 0,
                loop=0,
                quality=quality,
                method=4,
            )
            if Path(destination).stat().st_size <= limit:
                return
    raise ValueError(
        "El sticker supera el peso permitido. Reduce la duración o simplifica el contenido."
    )


def validate_sticker(path):
    with Image.open(path) as image:
        frames = getattr(image, "n_frames", 1)
        duration = 0
        issues = []
        if image.size != (512, 512):
            issues.append("Las dimensiones deben ser 512 × 512.")
        for index in range(frames):
            image.seek(index)
            image.load()
            if frames > 1:
                delay = image.info.get("duration", 0)
                duration += delay
                if delay < 8:
                    issues.append("Los cuadros deben durar al menos 8 ms.")
        size = Path(path).stat().st_size
        if size > (500_000 if frames > 1 else 100_000):
            issues.append("El sticker supera el peso permitido.")
        if duration > 10000:
            issues.append("La animación supera los 10 segundos.")
        return dict(
            valid=not issues,
            issues=list(dict.fromkeys(issues)),
            width=image.width,
            height=image.height,
            frames=frames,
            duration_ms=duration,
            bytes=size,
        )


def render_media(
    path, destination, options=None, cancelled=lambda: False, remove_background=None
):
    from .engine import StickerEngine

    options = options or {}
    info = media_info(path)
    start, end = clip_bounds(info, options.get("start", 0), options.get("end"))
    frames, durations = read_clip(path, info, start, end, cancelled)
    output = []
    engine = StickerEngine()
    try:
        for frame in frames:
            if cancelled():
                raise InterruptedError("Cancelled")
            frame.thumbnail((1024, 1024))
            if remove_background:
                original_alpha = frame.getchannel("A")
                from PIL import ImageChops

                removed = remove_background(frame)
                removed.putalpha(
                    ImageChops.multiply(original_alpha, removed.getchannel("A"))
                )
                frame = removed
            image = engine.transform_image_obj(
                frame, crop_mode=options.get("crop_mode", "fit")
            )
            scale = options.get("zoom", 1)
            if scale != 1:
                resized = image.resize(
                    (max(1, round(512 * scale)),) * 2, Image.Resampling.LANCZOS
                )
                image.close()
                image = Image.new("RGBA", (512, 512))
                image.paste(
                    resized, ((512 - resized.width) // 2, (512 - resized.height) // 2)
                )
                resized.close()
            if options.get("flip"):
                image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if options.get("rotate"):
                image = image.rotate(
                    -options["rotate"], resample=Image.Resampling.BICUBIC
                )
            shifted = Image.new("RGBA", (512, 512))
            shifted.paste(
                image, (round(options.get("x", 0)), round(options.get("y", 0)))
            )
            image.close()
            image = shifted
            text = options.get("text", "").strip()
            if text:
                font_id = options.get("font", "default")
                size = options.get("font_size", 40)
                font = (
                    ImageFont.truetype(str(FONT_ROOT / "comicneue.ttf"), size)
                    if font_id == "default"
                    else ImageFont.truetype(str(FONT_ROOT / (font_id + ".ttf")), size)
                )
                lines = []
                line = ""
                for char in text:
                    if char == "\n" or font.getlength(line + char) > 460:
                        lines.append(line)
                        line = ""
                    if char != "\n":
                        line += char
                if line:
                    lines.append(line)
                if len(lines) > 3:
                    raise ValueError(
                        "El texto ocupa más de tres líneas. Reduce el tamaño."
                    )
                draw = ImageDraw.Draw(image)
                for index, line in enumerate(lines):
                    draw.text(
                        (
                            256,
                            options.get("text_y", 432)
                            + (index - (len(lines) - 1) / 2) * size * 1.15,
                        ),
                        line,
                        font=font,
                        fill=options.get("text_color", "#ffffff"),
                        anchor="mm",
                        stroke_width=max(2, size // 10),
                        stroke_fill="#10213c",
                    )
            output.append(image)
        if not output:
            raise ValueError("No hay cuadros en el fragmento seleccionado.")
        encode_frames(output, durations, destination)
        report = validate_sticker(destination)
        if not report["valid"]:
            raise ValueError("; ".join(report["issues"]))
        return report
    finally:
        for frame in frames + output:
            frame.close()
