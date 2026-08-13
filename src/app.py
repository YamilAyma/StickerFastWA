import webview
import pyautogui
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, "logic"))
from sfwa import Sfwa

sfwa = Sfwa()


def run(window):
    try:
        width, height = pyautogui.size()
        window.move(width - 300, height - 510)
    except Exception as e:
        print(f"Error positioning window: {e}")


class Api:
    def __init__(self):
        self.cancel_heavy_stuff_flag = False

    def getUserPreferences(self):
        response = sfwa.get_user_preferences()
        return response

    def getLanguageJson(self, lang):
        response = sfwa.get_language_json(lang)
        return response

    def closeApp(self, user_preferences):
        sfwa.set_user_preferences(user_preferences)
        window.destroy()

    def minimizeApp(self):
        window.minimize()

    def selectFolder(self, dir):
        dialog_type = getattr(webview, 'FileDialog', webview).FOLDER if hasattr(webview, 'FileDialog') else webview.FOLDER_DIALOG
        response = window.create_file_dialog(
            dialog_type, directory=dir)
        if response and len(response) > 0:
            return response[0]
        return dir

    def selectIcon(self):
        dialog_type = getattr(webview, 'FileDialog', webview).OPEN if hasattr(webview, 'FileDialog') else webview.OPEN_DIALOG
        file_types = ('Image Files (*.jpg;*.png;*.webp)',
                      'All Files (*.jpg;*.png;*.webp)')
        file = window.create_file_dialog(
            dialog_type, allow_multiple=False, file_types=file_types)
        if file and len(file) > 0:
            icon_dir = file[0]
            response = {
                'dir': icon_dir,
                'encode': sfwa.create_encode_icon(icon_dir).decode()
            }
            return response
        return None

    def openFolder(self, folder):
        sfwa.open_folder(folder)

    def openLicense(self, lang):
        sfwa.open_license(lang)

    def openTerms(self, lang):
        sfwa.open_terms(lang)

    def openGithub(self):
        sfwa.open_github()

    def createPack(self, data):
        response = sfwa.create_pack(data)
        return response


if __name__ == '__main__':
    api = Api()
    html_path = os.path.join(BASE_DIR, "view", "index.html")
    window = webview.create_window("StickerFast WA", html_path,
                                   width=290, height=500, resizable=False, frameless=True,
                                   transparent=True, on_top=True, js_api=api, easy_drag=False)
    webview.start(run, window, http_server=True, debug=False)

