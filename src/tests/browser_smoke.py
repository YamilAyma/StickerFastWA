"""Run against system Chromium: venv/bin/python src/tests/browser_smoke.py."""
import io
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

from PIL import Image
from playwright.sync_api import sync_playwright, expect


def png(color):
    output = io.BytesIO()
    Image.new('RGB', (160, 120), color).save(output, 'PNG')
    return output.getvalue()


def run():
    repository = Path(__file__).resolve().parents[2]
    Path('/tmp/stickerfast-browser').mkdir(parents=True, exist_ok=True)
    chromium = shutil.which('chromium')
    if not chromium:
        raise RuntimeError('Install Chromium before running this browser check.')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    with tempfile.TemporaryFile() as log:
        server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'server.app:app', '--app-dir', 'src',
                                   '--host', '127.0.0.1', '--port', str(port)], cwd=repository,
                                  stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                try:
                    urllib.request.urlopen(base + '/api/health', timeout=1).close()
                    break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError('Server failed to start')
                    time.sleep(.1)
            else:
                raise RuntimeError('Server readiness timed out')
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=chromium, headless=True, args=['--no-sandbox'])
                try:
                    context = browser.new_context(viewport={'width': 1440, 'height': 1100}, reduced_motion='reduce')
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(base)
                    expect(page.get_by_role('heading', name='Elige tus stickers')).to_be_visible()
                    expect(page.locator('#create')).to_be_disabled()
                    for width in (320, 768, 1024, 1440):
                        page.set_viewport_size({'width': width, 'height': 1100})
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
                    page.screenshot(path='/tmp/stickerfast-browser/desktop-empty.png', full_page=True)
                    page.locator('#files').set_input_files([
                        {'name': 'red.png', 'mimeType': 'image/png', 'buffer': png('red')},
                        {'name': 'blue.png', 'mimeType': 'image/png', 'buffer': png('blue')},
                    ])
                    expect(page.locator('.media-card')).to_have_count(2)
                    page.get_by_role('checkbox', name='Incluir blue.png').uncheck()
                    expect(page.locator('#selected-count')).to_have_text('1 sticker')
                    page.locator('#name').fill('Browser pack')
                    page.locator('#author').fill('Browser test')
                    page.locator('#icon').set_input_files({'name':'icon.png', 'mimeType':'image/png', 'buffer':png('green')})
                    page.screenshot(path='/tmp/stickerfast-browser/desktop-files.png', full_page=True)
                    # A temporary polling failure must not lose the running job.
                    fail_once = [True]

                    def transient_status_error(route):
                        if route.request.method == 'GET' and fail_once[0]:
                            fail_once[0] = False
                            route.fulfill(status=503, json={'detail': 'Temporary failure'})
                        else:
                            route.continue_()

                    page.route(re.compile(base + r'/api/jobs/[a-f0-9]+$'), transient_status_error)
                    page.locator('#create').click()
                    expect(page.locator('#retry')).to_be_visible()
                    expect(page.locator('#create')).to_be_disabled()
                    page.locator('#retry').click()
                    expect(page.locator('#download')).to_be_visible(timeout=15000)
                    expect(page.locator('#job-title')).to_have_text('Tu pack está listo')
                    expect(page.locator('#job-percentage')).to_have_text('100 %')
                    with page.expect_download() as download_info:
                        page.locator('#download').click()
                    download = download_info.value
                    assert download.suggested_filename == 'Browser pack.wastickers'
                    with zipfile.ZipFile(download.path()) as archive:
                        assert archive.read('title.txt') == b'Browser pack'
                        assert sum(name.endswith('.webp') for name in archive.namelist()) == 1
                    # Reload recovers the completed job and optional browser preferences.
                    page.locator('#theme').click()
                    page.reload()
                    expect(page.locator('html')).to_have_attribute('data-theme', 'light')
                    expect(page.locator('#download')).to_be_visible()
                    expect(page.locator('#author')).to_have_value('Browser test')
                    page.locator('#delete-job').click()
                    expect(page.locator('#job-panel')).to_be_hidden()
                    page.set_viewport_size({'width':390, 'height':844})
                    expect(page.locator('#create')).to_be_disabled()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    page.screenshot(path='/tmp/stickerfast-browser/mobile-light.png', full_page=True)
                    # Exercise mobile Wemoji creation and remove/exclude interactions.
                    page.locator('#files').set_input_files({'name':'mobile.png', 'mimeType':'image/png', 'buffer':png('blue')})
                    page.locator('#name').fill('Mobile pack')
                    page.locator('#package').select_option('wemoji')
                    page.locator('#create').click()
                    expect(page.locator('#download')).to_be_visible(timeout=15000)
                    with page.expect_download() as download_info:
                        page.locator('#download').click()
                    with zipfile.ZipFile(download_info.value.path()) as archive:
                        assert any(name.endswith('.wspdata') for name in archive.namelist())
                    page.locator('#delete-job').click()
                    page.get_by_role('button', name='Quitar mobile.png').click()
                    expect(page.locator('.media-card')).to_have_count(0)
                    page.locator('#theme').click()
                    page.screenshot(path='/tmp/stickerfast-browser/mobile-dark.png', full_page=True)
                    headings = {
                        'en': 'Choose your stickers', 'fr': 'Choisissez vos stickers',
                        'de': 'Wähle deine Sticker', 'it': 'Scegli i tuoi sticker',
                        'pt': 'Escolha suas figurinhas', 'es': 'Elige tus stickers',
                    }
                    page.set_viewport_size({'width': 320, 'height': 844})
                    for language, heading in headings.items():
                        page.locator('#language').select_option(language)
                        expect(page.locator('html')).to_have_attribute('lang', language)
                        expect(page.locator('#media-title')).to_have_text(heading)
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), language
                    page.locator('#language').select_option('en')
                    page.reload()
                    expect(page.locator('html')).to_have_attribute('lang', 'en')
                    expect(page.locator('#media-title')).to_have_text('Choose your stickers')
                    page.locator('#files').set_input_files({'name':'invalid.png', 'mimeType':'image/png', 'buffer':b'invalid'})
                    page.locator('#name').fill('English pack')
                    page.locator('#author').fill('Test')
                    page.locator('#create').click()
                    expect(page.locator('#message')).to_contain_text('Could not read the file.')
                    page.locator('#clear').click()
                    page.locator('#files').set_input_files({'name':'english.png', 'mimeType':'image/png', 'buffer':png('red')})
                    page.locator('#crop-mode').select_option('fit')
                    page.locator('#create').click()
                    expect(page.locator('#job-title')).to_have_text('Your pack is ready', timeout=15000)
                    expect(page.locator('#download')).to_have_text('Download pack ↓')
                    page.locator('#language').select_option('fr')
                    expect(page.locator('#job-title')).to_have_text('Votre pack est prêt')
                    expect(page.locator('#download')).to_have_text('Télécharger le pack ↓')
                    page.locator('#delete-job').click()
                    assert not errors, errors
                    print('PASS: desktop/mobile creation, both formats, six languages, localized errors/status, preferences, reload and polling recovery; no JS errors')
                    context.close()
                finally:
                    browser.close()
        except BaseException:
            log.seek(0)
            print(log.read().decode(errors='replace')[-5000:], file=sys.stderr)
            raise
        finally:
            server.terminate()
            server.wait(timeout=15)


if __name__ == '__main__':
    run()
