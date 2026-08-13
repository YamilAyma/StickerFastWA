from PIL import Image, ImageDraw, GifImagePlugin, ImageChops
from os.path import isfile, join
from munch import DefaultMunch
from datetime import datetime
import numpy as np
import webbrowser
import subprocess
import platform
import zipfile
import base64
import shutil
import webp
import json
import os

try:
    from gi.repository import GLib
    HAS_GLIB = True
except ImportError:
    HAS_GLIB = False


class Sfwa:
    def __init__(self):
        global root
        root = os.getcwd()
        self.cancel_flag = False

    def cancel_processing(self):
        self.cancel_flag = True

    # ~ GET the user preferences for the GUI
    def get_user_preferences(self):
        file = os.path.join(root, "src", "data", "user.json")
        # open the file in read mode
        with open(file, "r") as read_file:
            data = json.load(read_file)  # load the data
            # create a response dict with the data
            response = {
                "lang": data["language"],
                "theme": data["theme"],
                "directory": data["directory"],
                "animatedIsShow": data["animatedIsShow"],
            }
        # verify if the directory is valid and if it is not valid, set the default pictures directory as the directory
        if response["directory"] == "" or not os.path.isdir(response["directory"]):
            response["directory"] = self.get_default_dir()
        return response  # return the response

    # ~ POST the user preferences for the GUI
    def set_user_preferences(self, data):
        if not isinstance(data, dict):
            return
        lang = data.get("lang") or data.get("language") or "es"
        theme = data.get("theme") or "dark"
        directory = data.get("directory") or ""
        animated_is_show = data.get("animatedIsShow", True)

        # modify the keys in data creating a new dict in the same variable
        data_to_save = {
            "language": lang,
            "theme": theme,
            "directory": directory,
            "animatedIsShow": animated_is_show,
        }
        file = os.path.join(root, "src", "data", "user.json")
        # open the file in write mode to overwrite the data
        with open(file, "w") as write_file:
            json.dump(data_to_save, write_file, indent=4)  # inserting the new data

    # ~ GET the language json file
    def get_language_json(self, lang):
        if not lang or not isinstance(lang, str):
            lang = "es"
        file = os.path.join(root, "src", "lang", f"{lang}.json")
        if not os.path.exists(file):
            file = os.path.join(root, "src", "lang", "es.json")
        with open(file, "r", encoding="utf-8") as read_file:
            response = json.load(read_file)
        return response

    # ~ return the default directory of the pictures
    def get_default_dir(self):
        # get the user operative system
        os_system = platform.system()
        # return dir of pictures folder
        if os_system == "Windows":
            return os.path.join(os.path.expanduser("~"), "Pictures").replace("\\", "/")
        elif os_system == "Linux" and HAS_GLIB:
            try:
                return GLib.get_user_special_dir(GLib.USER_DIRECTORY_PICTURES)
            except Exception:
                pass
        return os.path.join(os.path.expanduser("~"), "Pictures").replace("\\", "/")

    # ~ return string with the base64 of the image directory passed
    def create_encode_icon(self, icon):
        new_img = open(icon, "rb")  # open the file
        # encode the image in base64
        new_img_encode = base64.b64encode(new_img.read())
        new_img.close()
        return new_img_encode  # return the base64 of the image

    # ~ open the directory folder passed
    def open_folder(self, folder):
        # get the user operative system
        os_system = platform.system()
        # open the folder in the user operative system
        if os_system == "Windows":
            os.startfile(folder)
        elif os_system == "Linux":
            subprocess.Popen(["xdg-open", folder])

    # ~ open the license file in base of the language passed
    def open_license(self, lang):
        # get the directory of the licence in base lang param
        license = os.path.join(root, "src", "resources", "license", f"license_{lang}.pdf")
        # get the user operative system
        os_system = platform.system()
        # open the file in the user operative system
        if os_system == "Windows":
            os.startfile(license)
        elif os_system == "Linux":
            subprocess.Popen(["xdg-open", license])

    # ~ open the terms of use file in base of the language passed
    def open_terms(self, lang):
        # get the directory of the terms in base lang param
        terms = os.path.join(root, "src", "resources", "terms", f"terms_{lang}.pdf")
        # get the user operative system
        os_system = platform.system()
        # open the file in the user operative system
        if os_system == "Windows":
            os.startfile(terms)
        elif os_system == "Linux":
            subprocess.Popen(["xdg-open", terms])

    # ~ open the personal github
    def open_github(self):
        url = "https://github.com/FelipeGCx"
        webbrowser.open(url, new=2, autoraise=True)

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
        try:
            # evaluate the data app select for the user and call the function to create compatible the pack with that app
            if data.package == "stickerMaker":
                response = self.create_pack_sticker_maker(data, progress_callback=progress_callback, ignored_files=ignored_files)
            else:
                response = self.create_pack_wemoji(data, progress_callback=progress_callback, ignored_files=ignored_files)
        except Exception as e:
            print(f"Error creating pack: {e}")
            response = False
        finally:
            os.chdir(root)  # change to the root directory for the next operations
        return response  # return the response

    # ~ Create the pack for the wemoji app
    def create_pack_wemoji(self, data, progress_callback=None, ignored_files=None):
        # copy the compresed file to the directory of the user
        dir_origin = os.path.join(root, "src", "resources", "compressed")
        zip_file_name = "wemoji.wemojipack"
        self.copy_file(dir_origin, data.directory, zip_file_name)
        # change of directory to the directory of the user
        os.chdir(data.directory)
        # create a folder for the pack
        folder_name = self.create_name("WSP")
        os.mkdir(folder_name)
        # change of directory to the folder of the pack
        os.chdir(f"{data.directory}/{folder_name}")
        # create file .wspdata
        text_file = ".wspdata"
        icon_name = "tray_icon.png"
        # create the sentence to animated or regular pack
        if data.animated:
            sentence = {
                "a": folder_name,
                "b": data.namepack,
                "c": data.author,
                "d": "tray_icon.png",
                "i": "4",
                "j": False,
                "k": True,
            }
        else:
            sentence = {
                "a": folder_name,
                "b": data.namepack,
                "c": data.author,
                "d": icon_name,
                "i": "4",
                "j": False,
                "k": False,
            }
        # create the file .wspdata and write the sentence
        self.open_text_file(text_file, "w", sentence, is_json=True)
        # create icon
        img_icon = self.transform_image(data.icon, size=(96, 96), radius=16)
        img_icon.save(icon_name)
        img_icon.close()
        # process the lote of images
        self.process_images(data.directory, folder_name, data.animated, data.conserve, progress_callback=progress_callback, ignored_files=ignored_files)
        os.chdir(data.directory)
        # add the folder with all files in the zip file
        self.add_folder_to_zip(zip_file_name, folder_name)
        # rename the zip file to the name of the pack
        self.rename_pack(zip_file_name, data.namepack, "wemojipack")
        # remove the unessary folder
        folder_dir = f"{data.directory}/{folder_name}"
        shutil.rmtree(folder_dir)
        return True  # return the response

    # ~ Create the pack for the sticker maker app
    def create_pack_sticker_maker(self, data, progress_callback=None, ignored_files=None):
        # copy the compresed file to the directory of the user
        dir_origin = os.path.join(root, "src", "resources", "compressed")
        zip_file_name = "stickermaker.wastickers"
        self.copy_file(dir_origin, data.directory, zip_file_name)
        # change of directory to the directory of the user
        os.chdir(data.directory)
        # create a folder for the pack
        folder_name = self.create_name("WSP")
        os.mkdir(folder_name)
        # change of directory to the folder of the pack
        os.chdir(f"{data.directory}/{folder_name}")
        # create files for name pack and author
        namepack_file = f"title.txt"
        author_file = "author.txt"
        self.open_text_file(namepack_file, "a", data.namepack)
        self.open_text_file(author_file, "a", data.author)
        # create icon
        icon_name = "tray_icon.png"
        img_icon = self.transform_image(data.icon, size=(96, 96), radius=16)
        img_icon.save(icon_name)
        img_icon.close()
        # process the lote of images
        self.process_images(data.directory, folder_name, data.animated, data.conserve, progress_callback=progress_callback, ignored_files=ignored_files)
        os.chdir(data.directory)
        zip_dir = f"{data.directory}/{zip_file_name}"
        folder_dir = f"{data.directory}/{folder_name}"
        # add only the files in the zip file not the folder
        self.add_imgs_to_zip(zip_dir, folder_dir)
        os.chdir(data.directory)
        # rename the zip file to the name of the pack
        self.rename_pack(zip_file_name, data.namepack, "wastickers")
        # remove the unessary folder
        shutil.rmtree(folder_dir)
        return True  # return the response

    # ~ copy the file to the directory
    def copy_file(self, dir_origin, dir_to_move, file_name):
        # copy the file from directory origin to directory to move
        shutil.copy(os.path.join(dir_origin, file_name), os.path.join(dir_to_move, file_name))

    # ~ return string, with prefix pass and 17 numbers exaple sufix WS: WS20220712168203521
    def create_name(self, prefix):
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}"
        return f"{prefix}{timestamp}"

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
    def process_images(self, directory, destiny, animated=False, conserve_imgs=True, progress_callback=None, ignored_files=None):
        # change to the directory passed
        os.chdir(directory)
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
        for file in files:
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
                # validate the file is an animated image
                if self.validate_gif(file):
                    # transform and save the image to webp
                    self.transform_gif(file, destiny, file_name)
                elif self.validate_animated_webp(file):
                    # transform and save the image to webp
                    self.transform_webp(file, directory, destiny, file_name)
            else:
                # validate the file is an image
                if self.validate_img(file):
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
            name = f"{dir}{frame}.webp"
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
        self.webp_to_gif(f"{directory}/{file_name}", directory, name_gif)
        # transform the gif created to the sticker style and saved
        self.transform_gif(name_gif, destiny, save_name)
        # remove the gif created
        os.remove(f"{directory}{name_gif}")

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
        os.chdir(folder)
        for file in os.listdir(folder):
            self.add_to_pack(zip_file, file)

    # ~ add the file to the zip file in mode append
    def add_to_pack(self, zip_file, file):
        self.open_zip_file(zip_file, "a", file)

    # ~ remane the zip file to the new name with the extension passed
    def rename_pack(self, zip_file, new_name, file_extension):
        new_name = f"{new_name}.{file_extension}"
        os.rename(zip_file, new_name)
