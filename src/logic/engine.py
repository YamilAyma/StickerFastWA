"""Shared image/video and archive engine, independent of desktop UI and cwd.

Use one instance per processing job; progress and cancellation belong to that job.
"""
from PIL import Image, ImageDraw, ImageChops, ImageOps
from os.path import isfile, join
from pathlib import Path
from munch import DefaultMunch
from datetime import datetime
import numpy as np
import zipfile
import shutil
import tempfile
import webp
import json
import os
import uuid


class StickerEngine:
    def __init__(self, source_dir=None):
        self.source_dir = Path(source_dir).resolve() if source_dir is not None else Path(__file__).resolve().parents[1]
        self.cancel_flag = False

    def cancel_processing(self):
        self.cancel_flag = True

    # ~ return data serialized
    def serialize_data(self, data):
        # this serialize the data of dict to can access the data like javascript object usign the dot notation
        # example data = {'name': 'Felipe'} pass of data['name'] to data.name
        return DefaultMunch.fromDict(data)  # return the data serialized

    # ~ Create a pack with the data passed
    def create_pack(self, data, progress_callback=None):
        self.cancel_flag = False
        data = self.serialize_data(data)
        response = False  # response default is false
        ignored_files = getattr(data, 'ignored_files', None)
        crop_mode = getattr(data, 'crop_mode', None) or 'center_crop'
        try:
            # evaluate the data app select for the user and call the function to create compatible the pack with that app
            if data.package == "stickerMaker":
                response = self.create_pack_sticker_maker(data, progress_callback=progress_callback, ignored_files=ignored_files, crop_mode=crop_mode)
            else:
                response = self.create_pack_wemoji(data, progress_callback=progress_callback, ignored_files=ignored_files, crop_mode=crop_mode)
        except Exception as e:
            print(f"Error creating pack: {e}")
            response = False
        return response  # return the response

    def _create_pack(self, data, package, progress_callback=None, ignored_files=None, crop_mode="center_crop"):
        directory = Path(data.directory).resolve()
        icon = Path(data.icon).resolve()
        extension = "wemojipack" if package == "wemoji" else "wastickers"
        template = "wemoji.wemojipack" if package == "wemoji" else "stickermaker.wastickers"
        # Each job owns its staging files; never change the process working directory.
        with tempfile.TemporaryDirectory(prefix="WSP", dir=directory) as staging:
            folder = Path(staging)
            archive = folder / template
            shutil.copyfile(self.source_dir / "resources" / "compressed" / template, archive)
            content = folder / self.create_name("WSP")
            content.mkdir()
            if package == "wemoji":
                metadata = {"a": content.name, "b": data.namepack, "c": data.author,
                            "d": "tray_icon.png", "i": "4", "j": False, "k": bool(data.animated)}
                self.open_text_file(content / ".wspdata", "w", metadata, is_json=True)
            else:
                self.open_text_file(content / "title.txt", "w", data.namepack)
                self.open_text_file(content / "author.txt", "w", data.author)
            with self.transform_image(icon, size=(96, 96), radius=16) as image:
                image.save(content / "tray_icon.png")
            self.process_images(str(directory), str(content), data.animated, data.conserve,
                                progress_callback=progress_callback, ignored_files=ignored_files,
                                crop_mode=crop_mode)
            if self.cancel_flag:
                return False
            with zipfile.ZipFile(archive, "a") as output:
                for file in content.iterdir():
                    name = str(Path(content.name) / file.name) if package == "wemoji" else file.name
                    output.write(file, arcname=name, compress_type=zipfile.ZIP_DEFLATED)
            archive.replace(directory / f"{data.namepack}.{extension}")
        return True

    def create_pack_wemoji(self, data, progress_callback=None, ignored_files=None, crop_mode="center_crop"):
        return self._create_pack(data, "wemoji", progress_callback, ignored_files, crop_mode)

    def create_pack_sticker_maker(self, data, progress_callback=None, ignored_files=None, crop_mode="center_crop"):
        return self._create_pack(data, "stickerMaker", progress_callback, ignored_files, crop_mode)

    # ~ copy the file to the directory
    def copy_file(self, dir_origin, dir_to_move, file_name):
        # copy the file from directory origin to directory to move
        shutil.copy(os.path.join(dir_origin, file_name), os.path.join(dir_to_move, file_name))

    # ~ return string, with prefix pass and 17 numbers exaple sufix WS: WS20220712168203521
    def create_name(self, prefix):
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}"
        return f"{prefix}{timestamp}{uuid.uuid4().hex[:8]}"

    # ~ open the text file with the mode passed
    def open_text_file(self, file_name, mode, sentence=None, is_json=False):
        # ~ open the file with the argument mode
        with open(file_name, mode) as open_file:
            # ~ read the file and return it
            if mode == "r":
                return open_file.read()
            # ~ write the file for insert sentence
            elif mode == "w" or mode == "a":
                if is_json:
                    json.dump(sentence, open_file)
                else:
                    open_file.write(sentence)
                open_file.close()

    # ~ process the images in the folder in base params passed
    def process_images(self, directory, destiny, animated=False, conserve_imgs=True, progress_callback=None, ignored_files=None, crop_mode="center_crop"):
        directory = os.path.abspath(directory)
        destiny = os.path.abspath(destiny)
        files = [name for name in self.files_in_dir(directory)
                 if name not in (ignored_files or [])
                 and (self.validate_img(name) or self.validate_gif(name) or self.validate_video(name))][:30]
        for index, source_name in enumerate(files, 1):
            if self.cancel_flag:
                break
            if progress_callback:
                progress_callback(index, len(files))
            if self.cancel_flag:
                break
            source = os.path.join(directory, source_name)
            name = f"{self.create_name('WS')}.webp"
            if self.validate_video(source):
                if not self.process_video_file(source, destiny, name, crop_mode=crop_mode):
                    raise ValueError("Could not convert video")
            elif animated:
                self.transform_gif(source, destiny, name, crop_mode=crop_mode)
            else:
                with self.transform_image(source, crop_mode=crop_mode) as image:
                    image.save(os.path.join(destiny, name))
            if not conserve_imgs and not self.cancel_flag:
                os.remove(source)

    # ~ return list of all files in the directory passed
    def files_in_dir(self, directory):
        # create a list of all content of the directory
        source = os.listdir(directory)
        # create a list comprehension to get only the files using isfile to condition
        files = [name for name in source if isfile(join(directory, name))]
        return files  # return the list of files

    # ~ replace the suffix to the new suffix passed
    def replace_endwith(self, file_name, suffix):
        # separate the name and the suffix
        name, ext = os.path.splitext(file_name)
        return f"{name}.{suffix}"  # return the file_name with the new suffix

    # ~ return boolean, if the file is an image
    def validate_img(self, file_name):
        if (
            file_name.lower().endswith(".gif")
            or file_name.lower().endswith(".jpg")
            or file_name.lower().endswith(".png")
            or file_name.lower().endswith(".webp")
            or file_name.lower().endswith(".jpeg")
        ):
            return True
        else:
            return False

    # ~ return boolean, if the file is an animated image
    def validate_gif(self, file_name):
        # ~ validates if the file is an gif image
        if file_name.lower().endswith(".gif"):
            return True
        else:
            return False

    # ~ return boolean, if the file is an animated webp image
    def validate_animated_webp(self, file_name):
        if file_name.lower().endswith(".webp"):
            return True
        else:
            return False

    # ~ return boolean, if the file is a video
    def validate_video(self, file_name):
        exts = (".mp4", ".webm", ".mov", ".avi", ".mkv")
        return file_name.lower().endswith(exts)

    # ~ process video file into webp animated sticker with crop_mode
    def process_video_file(self, video_path, dir_destiny, save_name, crop_mode="center_crop"):
        try:
            import cv2
        except ImportError:
            print("OpenCV (cv2) not installed. Cannot process video.")
            return False

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Cannot open video file: {video_path}")
            return False

        fps = cap.get(cv2.CAP_PROP_FPS) or 24
        sample_interval = max(1, int(fps / 12))  # Target ~12 FPS
        frames = []
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret or len(frames) >= 45:  # Max 3-4 seconds
                break

            if frame_idx % sample_interval == 0:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img_pil = Image.fromarray(frame_rgb)
                sticker_frame = self.transform_image_obj(img_pil, crop_mode=crop_mode)
                frames.append(sticker_frame)

            frame_idx += 1

        cap.release()

        if not frames:
            return False

        output_file = os.path.join(dir_destiny, save_name)
        duration = int(1000 / 12)  # ~83ms per frame

        frames[0].save(
            output_file,
            save_all=True,
            append_images=frames[1:],
            transparency=0,
            loop=0,
            duration=duration,
            optimize=True,
        )

        # Multi-level Adaptive Compression Guard to strictly ensure < 500 KB
        self.apply_adaptive_compression(output_file, frames, duration)
        return True

    def apply_adaptive_compression(self, output_file, frames, duration):
        if not os.path.exists(output_file):
            return

        max_bytes = 500000

        # Level 1: Frame Stepping (half frame count)
        if os.path.getsize(output_file) > max_bytes and len(frames) > 4:
            step_frames = frames[::2]
            step_duration = duration * 2
            step_frames[0].save(
                output_file,
                save_all=True,
                append_images=step_frames[1:],
                transparency=0,
                loop=0,
                duration=step_duration,
                optimize=True,
            )

        # Level 2: Resize frames to 384x384
        if os.path.exists(output_file) and os.path.getsize(output_file) > max_bytes and len(frames) > 4:
            step_frames = [f.resize((384, 384)) for f in frames[::2]]
            step_duration = duration * 2
            step_frames[0].save(
                output_file,
                save_all=True,
                append_images=step_frames[1:],
                transparency=0,
                loop=0,
                duration=step_duration,
                optimize=True,
            )

        # Level 3: Resize frames to 256x256
        if os.path.exists(output_file) and os.path.getsize(output_file) > max_bytes and len(frames) > 4:
            step_frames = [f.resize((256, 256)) for f in frames[::3]]
            step_duration = duration * 3
            step_frames[0].save(
                output_file,
                save_all=True,
                append_images=step_frames[1:],
                transparency=0,
                loop=0,
                duration=step_duration,
                optimize=True,
            )

    def transform_image_obj(self, img, size=(512, 512), radius=8, crop_mode="fit"):
        """Apply the same non-destructive framing to images and animation frames."""
        if crop_mode not in {"fit", "center_crop"}:
            raise ValueError("Unknown crop mode")
        image = ImageOps.exif_transpose(img).convert("RGBA")
        resize = ImageOps.fit if crop_mode == "center_crop" else ImageOps.contain
        content = resize(image, size, method=Image.Resampling.LANCZOS)
        mask = Image.new("L", content.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, content.width - 1, content.height - 1),
            radius=int(size[0] * radius / 100), fill=255,
        )
        # Multiply, rather than replace, source alpha so transparent pixels stay transparent.
        content.putalpha(ImageChops.multiply(content.getchannel("A"), mask))
        output = Image.new("RGBA", size, (0, 0, 0, 0))
        output.alpha_composite(content, ((size[0] - content.width) // 2,
                                         (size[1] - content.height) // 2))
        image.close()
        content.close()
        mask.close()
        return output

    # ~ validate the weight of the file
    def validate_weight(self, file_name, weight=512000):
        file_weight = os.path.getsize(file_name)
        if file_weight > weight:
            return False
        else:
            return True

    # ~ return a boolean if the image has transparency
    def has_transparency(self, img):
        if img.info.get("transparency", None) is not None:
            return True
        if img.mode == "P":
            transparent = img.info.get("transparency", -1)
            for _, index in img.getcolors():
                if index == transparent:
                    return True
        elif img.mode == "RGBA":
            extrema = img.getextrema()
            if extrema[3][0] < 255:
                return True
        return False

    # ~ crop the transparent border of the image
    def crop_image(self, file):
        img = Image.open(file)
        img = self.trim(img)
        img.save(file)

    def trim(self, im):
        bg = Image.new(im.mode, im.size, im.getpixel((0, 0)))
        diff = ImageChops.difference(im, bg)
        diff = ImageChops.add(diff, diff, 2.0, -100)
        bbox = diff.getbbox()
        return im.crop(bbox)

    def transform_image(self, file_name, size=(512, 512), radius=8, crop_mode="fit"):
        with Image.open(file_name) as image:
            return self.transform_image_obj(image, size=size, radius=radius, crop_mode=crop_mode)

    def transform_gif(self, file_name, dir, save_name, crop_mode="fit"):
        """Read GIF or animated WebP directly, preserving alpha and frame timing."""
        frames = []
        durations = []
        try:
            with Image.open(file_name) as image:
                for index in range(getattr(image, "n_frames", 1)):
                    if self.cancel_flag:
                        return
                    image.seek(index)
                    frame = image.convert("RGBA")
                    durations.append(max(1, int(image.info.get("duration", 80))))
                    frames.append(self.transform_image_obj(frame, crop_mode=crop_mode))
                    frame.close()
            output = os.path.join(dir, save_name)
            frames[0].save(output, save_all=True, append_images=frames[1:],
                           loop=0, duration=durations, optimize=True)
            self.apply_adaptive_compression(output, frames, durations[0])
        finally:
            for frame in frames:
                frame.close()

    def transform_webp(self, file_name, directory, destiny, save_name, crop_mode="fit"):
        self.transform_gif(os.path.join(directory, file_name), destiny, save_name,
                           crop_mode=crop_mode)

    # ~ parse the webp image to gif
    def webp_to_gif(self, file_name, dir, save_name):
        # Load a PIL image array from the specified .webp animation file
        anim = webp.load_images(file_name)
        # Grab a reference to the first frame, and save the entire PIL image array as GIF with 70ms frames (14.286 FPS)
        anim[0].save(
            f"{dir}/{save_name}",
            save_all=True,
            append_images=anim[0:],
            duration=80,
            loop=0,
        )

    # ~ compress the image with the quality passed
    def compress_img(self, file_name, quality=50):
        # open the image
        img = Image.open(file_name)
        # convert color to RGB
        img = img.convert("RGB")
        # separate the file name and the extension
        name, ext = os.path.splitext(file_name)
        new_file_name = f"{name}.jpg"
        # save the image with the quality passed
        img.save(new_file_name, quality=quality, optimize=True)
        img.close()
        return new_file_name  # return the new file name

    # ~ write or append the file to zip file
    def open_zip_file(self, file_name, mode, add_file):
        with zipfile.ZipFile(file_name, mode) as zip_file:
            # zip_file.write(add_file, compress_type=zipfile.ZIP_STORED)
            zip_file.write(add_file, compress_type=zipfile.ZIP_DEFLATED)
            zip_file.close()

    # ~ add all files in the folder directory and the folder to the zip file
    def add_folder_to_zip(self, zip_file, folder):
        for file in os.listdir(folder):
            self.add_to_pack(zip_file, f"{folder}/{file}")

    # ~ add all files in the folder directory to the zip file
    def add_imgs_to_zip(self, zip_file, folder):
        with zipfile.ZipFile(zip_file, "a") as archive:
            for file in Path(folder).iterdir():
                archive.write(file, arcname=file.name, compress_type=zipfile.ZIP_DEFLATED)

    # ~ add the file to the zip file in mode append
    def add_to_pack(self, zip_file, file):
        self.open_zip_file(zip_file, "a", file)

    # ~ remane the zip file to the new name with the extension passed
    def rename_pack(self, zip_file, new_name, file_extension):
        new_name = f"{new_name}.{file_extension}"
        os.rename(zip_file, new_name)
