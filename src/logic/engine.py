"""Shared image/video and archive engine, independent of desktop UI and cwd.

Use one instance per processing job; progress and cancellation belong to that job.
"""
from PIL import Image, ImageDraw, GifImagePlugin, ImageChops
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
        crop_mode = getattr(data, 'crop_mode', 'center_crop')
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
        # list the image files in the directory
        all_files = self.files_in_dir(directory)
        if ignored_files:
            files = [f for f in all_files if f not in ignored_files]
        else:
            files = all_files

        total_files = min(len(files), 30)
        checker = 0  # checker for the number of files in the directory
        file_format = "webp"  # define the final format to the image

        # iterate the image files in the directory
        for source_name in files:
            file = os.path.join(directory, source_name)
            if self.cancel_flag:
                print("Pack creation cancelled by user flag.")
                break

            checker += 1  # increment the checker
            if progress_callback:
                try:
                    progress_callback(checker, total_files)
                except Exception as p_err:
                    print(f"Progress callback error: {p_err}")

            # check if the number of files is greater than 30
            if checker > 30:
                break
            # create the name for the image
            file_name = f"{self.create_name('WS')}.{file_format}"
            # check if the pack is animated
            if animated:
                # validate the file is an animated image or video
                if self.validate_gif(file):
                    # transform and save the image to webp
                    self.transform_gif(file, destiny, file_name)
                elif self.validate_video(file):
                    # transform video to animated webp with chosen crop_mode
                    self.process_video_file(file, destiny, file_name, crop_mode=crop_mode)
                elif self.validate_animated_webp(file):
                    # transform and save the image to webp
                    self.transform_webp(file, directory, destiny, file_name)
            else:
                # validate the file is an image or video
                if self.validate_video(file):
                    self.process_video_file(file, destiny, file_name, crop_mode=crop_mode)
                elif self.validate_img(file):
                    # check if the image is a .webp
                    if file.endswith(".webp"):
                        # open the image and only rezise it
                        img = Image.open(file)
                        img = img.resize((512, 512))
                        img.save(f"{destiny}/{file_name}")
                        img.close()
                    elif file.endswith(".png"):
                        img_png = Image.open(file)
                        has_transparency = self.has_transparency(img_png)
                        img_png.close()
                        if has_transparency:
                            # crop the transparent border of the image
                            self.crop_image(file)
                        # transform and save the image to webp
                        img = self.transform_image(file)
                        img.save(f"{destiny}/{file_name}")
                        img.close()
                    else:
                        # transform and save the image to webp
                        img = self.transform_image(file)
                        img.save(f"{destiny}/{file_name}")
                        img.close()
            # check if the conserve the images
            if not conserve_imgs:
                try:
                    os.remove(file)  # remove the image
                except Exception:
                    pass

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
            file_name.endswith(".jpg")
            or file_name.endswith(".png")
            or file_name.endswith(".webp")
            or file_name.endswith(".jpeg")
        ):
            return True
        else:
            return False

    # ~ return boolean, if the file is an animated image
    def validate_gif(self, file_name):
        # ~ validates if the file is an gif image
        if file_name.endswith(".gif"):
            return True
        else:
            return False

    # ~ return boolean, if the file is an animated webp image
    def validate_animated_webp(self, file_name):
        if file_name.endswith(".webp"):
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
                h, w, _ = frame_rgb.shape

                if crop_mode == "center_crop":
                    # Exact 1:1 Center Crop
                    side = min(h, w)
                    x_start = (w - side) // 2
                    y_start = (h - side) // 2
                    cropped = frame_rgb[y_start:y_start+side, x_start:x_start+side]
                    img_pil = Image.fromarray(cropped)
                else:
                    # Fit original aspect ratio
                    img_pil = Image.fromarray(frame_rgb)

                img_pil = img_pil.convert("RGBA")
                sticker_frame = self.transform_image_obj(img_pil)
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

    def transform_image_obj(self, img, size=(512, 512), radius=8):
        radius = int(size[0] / 100 * radius)
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        width, heigth = img.size
        value_resize = (size[0], int(heigth * size[0] / width)) if width > heigth else (int(width * size[1] / heigth), size[1])
        if width < size[0] or heigth < size[0]:
            img = img.resize(value_resize)
        img.thumbnail(size)
        mask = Image.new("L", img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((0, 0) + img.size, radius=radius, fill=255)
        img_masked = Image.new("RGBA", size, (0, 0, 0, 0))
        img_masked.paste(img, mask=mask)
        img_output = Image.new("RGBA", size, (0, 0, 0, 0))
        x = int((size[0] - img.size[0]) / 2)
        y = int((size[1] - img.size[1]) / 2)
        img_output.paste(img_masked, (x, y))
        mask.close()
        img_masked.close()
        return img_output

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

    # ~ return an Pillow image object transformed to params passed
    def transform_image(self, file_name, size=(512, 512), radius=8):
        # convert the radius to the size of the image
        radius = int(size[0] / 100 * radius)
        # open the image
        img = Image.open(file_name)
        # parse the color of the image
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        # get the size of the image
        width, heigth = img.size
        # create a correct dimensions
        value_resize = (size[0], int(heigth * size[0] / width)) if width > heigth else (int(width * size[1] / heigth), size[1])
        if width < size[0] or heigth < size[0]:
            img = img.resize(value_resize)
        # make the thumbnail of the image to conserve the proportions
        img.thumbnail(size)
        mask = Image.new("L", img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((0, 0) + img.size, radius=radius, fill=255)
        img_masked = Image.new("RGBA", size, (0, 0, 0, 0))
        img_masked.paste(img, mask=mask)
        img_output = Image.new("RGBA", size, (0, 0, 0, 0))
        x = int((size[0] - img.size[0]) / 2)
        y = int((size[1] - img.size[1]) / 2)
        img_output.paste(img_masked, (x, y))
        img.close()
        mask.close()
        img_masked.close()
        return img_output

    # ~ transform the animated image
    def transform_gif(self, file_name, dir, save_name):
        GifImagePlugin.LOADING_STRATEGY = GifImagePlugin.LoadingStrategy.RGB_AFTER_FIRST
        img = Image.open(file_name)
        duration = img.info.get("duration", 80)
        frames = []
        for frame in range(0, img.n_frames):
            img.seek(frame)
            name = os.path.join(dir, f"frame-{frame}.webp")
            img.save(name)
            frames.append(self.transform_image(name))
            try:
                os.remove(name)
            except Exception:
                pass
        
        output_file = os.path.join(dir, save_name)
        frames[0].save(
            output_file,
            save_all=True,
            append_images=frames,
            transparency=0,
            loop=0,
            duration=duration,
            optimize=True,
        )
        img.close()

        # Adaptive Compression Guard for < 500 KB Limit
        if os.path.exists(output_file) and os.path.getsize(output_file) > 500000 and len(frames) > 2:
            step_frames = frames[::2]
            step_duration = duration * 2
            step_frames[0].save(
                output_file,
                save_all=True,
                append_images=step_frames,
                transparency=0,
                loop=0,
                duration=step_duration,
                optimize=True,
            )
            if os.path.getsize(output_file) > 500000:
                resized_frames = [f.resize((350, 350)) for f in step_frames]
                resized_frames[0].save(
                    output_file,
                    save_all=True,
                    append_images=resized_frames,
                    transparency=0,
                    loop=0,
                    duration=step_duration,
                    optimize=True,
                )

    # ~ transform the webp animated image
    def transform_webp(self, file_name, directory, destiny, save_name):
        name_gif = "webp_to_gif.gif"
        # convert the webp to gif
        with tempfile.TemporaryDirectory(dir=destiny) as temporary:
            self.webp_to_gif(os.path.join(directory, file_name), temporary, name_gif)
            self.transform_gif(os.path.join(temporary, name_gif), destiny, save_name)

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
