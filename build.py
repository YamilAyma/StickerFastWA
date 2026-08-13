import os
import subprocess
import sys


def build():
    print("Building StickerFastWA standalone executable distribution...")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app_script = os.path.join(base_dir, "src", "app.py")

    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    sep = ";" if sys.platform == "win32" else ":"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "StickerFastWA",
        "--add-data", f"{os.path.join(base_dir, 'src', 'view')}{sep}src/view",
        "--add-data", f"{os.path.join(base_dir, 'src', 'lang')}{sep}src/lang",
        "--add-data", f"{os.path.join(base_dir, 'src', 'data')}{sep}src/data",
        "--add-data", f"{os.path.join(base_dir, 'src', 'resources')}{sep}src/resources",
        app_script
    ]

    print(f"Running command: {' '.join(cmd)}")
    subprocess.check_call(cmd)
    print("\nSUCCESS: Portable application created in dist/StickerFastWA/")


if __name__ == "__main__":
    build()
