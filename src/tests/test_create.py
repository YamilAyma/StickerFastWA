import sys
import os
import shutil
import tempfile
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from logic.sfwa import Sfwa


def run_test():
    sfwa = Sfwa()

    with tempfile.TemporaryDirectory() as temp_dir:
        img_path = os.path.join(temp_dir, "sample.png")
        icon_path = os.path.join(temp_dir, "icon.png")

        img = Image.new("RGBA", (400, 400), color=(255, 0, 0, 255))
        img.save(img_path)
        img.save(icon_path)

        # 1. Test Sticker Maker (.wastickers)
        data_sm = {
            "package": "stickerMaker",
            "animated": False,
            "namepack": "TestStickerMaker",
            "author": "TestAuthor",
            "directory": temp_dir,
            "icon": icon_path,
            "conserve": True,
        }

        res_sm = sfwa.create_pack(data_sm)
        print(f"Sticker Maker Pack creation result: {res_sm}")
        sm_file = os.path.join(temp_dir, "TestStickerMaker.wastickers")
        assert res_sm is True and os.path.isfile(sm_file), f"Failed to create {sm_file}"
        print(f"SUCCESS: Created {sm_file}")

        # 2. Test Wemoji (.wemojipack)
        data_we = {
            "package": "wemoji",
            "animated": False,
            "namepack": "TestWemoji",
            "author": "TestAuthor",
            "directory": temp_dir,
            "icon": icon_path,
            "conserve": True,
        }

        res_we = sfwa.create_pack(data_we)
        print(f"Wemoji Pack creation result: {res_we}")
        we_file = os.path.join(temp_dir, "TestWemoji.wemojipack")
        assert res_we is True and os.path.isfile(we_file), f"Failed to create {we_file}"
        print(f"SUCCESS: Created {we_file}")


if __name__ == '__main__':
    run_test()

 