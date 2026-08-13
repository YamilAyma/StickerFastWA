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
        file_types = (
            'Image Files (*.png;*.jpg;*.jpeg;*.webp)',
            'All Files (*.*)'
        )
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

    def cancelProcessing(self):
        sfwa.cancel_processing()
        return True

    def getFolderImages(self, folder):
        if not folder or not os.path.isdir(folder):
            return []
        try:
            from PIL import Image
            import io
            import base64
            files = sfwa.files_in_dir(folder)
            valid_imgs = [f for f in files if sfwa.validate_img(f) or sfwa.validate_gif(f)][:30]
            result = []
            for f in valid_imgs:
                full_path = os.path.join(folder, f)
                try:
                    with Image.open(full_path) as img:
                        img.thumbnail((96, 96))
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        b64 = base64.b64encode(buf.getvalue()).decode()
                        result.append({"name": f, "encode": b64})
                except Exception as err:
                    print(f"Error encoding thumbnail for {f}: {err}")
            return result
        except Exception as e:
            print(f"Error getting folder images: {e}")
            return []

    def openFolder(self, folder):
        sfwa.open_folder(folder)

    def openLicense(self, lang):
        sfwa.open_license(lang)

    def openTerms(self, lang):
        sfwa.open_terms(lang)

    def openGithub(self):
        sfwa.open_github()

    def createPack(self, data):
        def progress_cb(current, total):
            percent = int((current / total) * 100) if total > 0 else 0
            try:
                window.evaluate_js(f"if (typeof updateProgress === 'function') updateProgress({percent}, {current}, {total});")
            except Exception:
                pass

        response = sfwa.create_pack(data, progress_callback=progress_cb)
        return response


if __name__ == '__main__':
    api = Api()
    html_path = os.path.join(BASE_DIR, "view", "index.html")
    window = webview.create_window("StickerFast WA", html_path,
                                   width=290, height=500, resizable=False, frameless=True,
                                   transparent=True, on_top=True, js_api=api, easy_drag=False)
    webview.start(run, window, http_server=True, debug=False)

