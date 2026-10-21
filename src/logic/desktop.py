"""Desktop-only preferences, folder dialogs support and OS integration."""
import base64
import json
import os
import platform
import subprocess
import webbrowser

try:
    from gi.repository import GLib
    HAS_GLIB = True
except ImportError:
    HAS_GLIB = False


class DesktopIntegration:
    # ~ GET the user preferences for the GUI
    def get_user_preferences(self):
        file = str(self.preferences_path)
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
        file = str(self.preferences_path)
        # open the file in write mode to overwrite the data
        with open(file, "w") as write_file:
            json.dump(data_to_save, write_file, indent=4)  # inserting the new data

    # ~ GET the language json file
    def get_language_json(self, lang):
        if not lang or not isinstance(lang, str):
            lang = "es"
        file = os.path.join(self.source_dir, "lang", f"{lang}.json")
        if not os.path.exists(file):
            file = os.path.join(self.source_dir, "lang", "es.json")
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
        license = os.path.join(self.source_dir, "resources", "license", f"license_{lang}.pdf")
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
        terms = os.path.join(self.source_dir, "resources", "terms", f"terms_{lang}.pdf")
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

