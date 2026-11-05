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
                    page.locator('#phone-access').click()
                    expect(page.locator('#phone-dialog')).to_be_visible()
                    expect(page.locator('#phone-status')).to_contain_text('Start StickerFast LAN')
                    page.locator('#phone-close').click()
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
                    # Editing stays in a draft until saved; erasing is undoable.
                    edit = page.get_by_role('button', name='Editar imagen').first
                    edit.click()
                    expect(page.locator('#image-editor')).to_be_visible()
                    expect(page.locator('#editor-save')).to_be_enabled()
                    page.locator('#editor-text').fill('Discard me')
                    page.keyboard.press('Escape')
                    expect(page.locator('#image-editor')).to_be_hidden()
                    expect(page.locator('.media-meta label span').first).to_have_text('red.png')
                    edit.click()
                    expect(page.locator('#editor-save')).to_be_enabled()
                    # Exercise recovery and undo with a deterministic segmentation response.
                    removed = io.BytesIO()
                    Image.new('RGBA', (512,512), (0,0,0,0)).save(removed, 'PNG')
                    requests = [0]
                    def background_response(route):
                        requests[0] += 1
                        if requests[0] == 1:
                            route.fulfill(status=503,json={'detail':'No se pudo quitar el fondo. La primera vez se necesita Internet para descargar el modelo.'})
                        else:
                            route.fulfill(status=200,content_type='image/png',body=removed.getvalue())
                    page.route('**/api/remove-background', background_response)
                    page.locator('#editor-remove-bg').click()
                    expect(page.locator('#editor-error')).to_be_visible()
                    expect(page.locator('#editor-remove-bg')).to_be_enabled()
                    assert page.locator('#editor-canvas').evaluate("c => c.getContext('2d').getImageData(256,256,1,1).data[3]") == 255
                    page.locator('#editor-remove-bg').click()
                    expect(page.locator('#editor-remove-bg')).to_be_enabled()
                    assert page.locator('#editor-canvas').evaluate("c => c.getContext('2d').getImageData(256,256,1,1).data[3]") == 0
                    page.locator('#editor-undo').click()
                    assert page.locator('#editor-canvas').evaluate("c => c.getContext('2d').getImageData(256,256,1,1).data[3]") == 255
                    page.locator('[data-tool="erase"]').click()
                    box = page.locator('#editor-canvas').bounding_box()
                    cx, cy = box['x'] + box['width']/2, box['y'] + box['height']/2
                    page.mouse.move(cx, cy)
                    page.mouse.down()
                    page.mouse.move(cx+2, cy+2)
                    page.mouse.up()
                    assert page.locator('#editor-canvas').evaluate("c => c.getContext('2d').getImageData(256,256,1,1).data[3]") == 0
                    page.locator('#editor-undo').click()
                    assert page.locator('#editor-canvas').evaluate("c => c.getContext('2d').getImageData(256,256,1,1).data[3]") == 255
                    page.locator('#editor-circle').click()
                    page.locator('#editor-save').click()
                    expect(page.get_by_role('button', name='Restaurar original')).to_be_visible()
                    page.get_by_role('button', name='Restaurar original').click()
                    expect(page.locator('.media-meta label span').first).to_have_text('red.png')
                    page.get_by_role('button', name='Editar imagen').first.click()
                    expect(page.locator('#editor-save')).to_be_enabled()
                    # A freehand cut keeps only the polygon interior.
                    page.locator('[data-tool="cut"]').click()
                    box = page.locator('#editor-canvas').bounding_box()
                    points = [(128,128),(384,128),(384,384),(128,384),(128,128)]
                    page.mouse.move(box['x']+points[0][0]*box['width']/512, box['y']+points[0][1]*box['height']/512)
                    page.mouse.down()
                    for x,y in points[1:]:
                        page.mouse.move(box['x']+x*box['width']/512, box['y']+y*box['height']/512, steps=3)
                    page.mouse.up()
                    assert page.locator('#editor-canvas').evaluate("c => c.getContext('2d').getImageData(64,256,1,1).data[3]") == 0
                    page.locator('#editor-text').fill('Hola')
                    page.locator('#editor-border').fill('4')
                    page.screenshot(path='/tmp/stickerfast-browser/editor-desktop.png', full_page=True)
                    page.locator('#editor-save').click()
                    expect(page.locator('#image-editor')).to_be_hidden(timeout=15000)
                    assert not errors, errors
                    expect(page.locator('.media-meta label span').first).to_have_text('red-editado.png', timeout=15000)
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
                    fail_preview_once = [True]

                    def transient_preview_error(route):
                        if fail_preview_once[0]:
                            fail_preview_once[0] = False
                            route.fulfill(status=503, json={'detail': 'Temporary failure'})
                        else:
                            route.continue_()

                    page.route(re.compile(base + r'/api/jobs/[a-f0-9]+/stickers$'), transient_preview_error)
                    page.locator('#create').click()
                    expect(page.locator('#retry')).to_be_visible()
                    expect(page.locator('#create')).to_be_enabled()
                    page.locator('#retry').click()
                    expect(page.locator('#download')).to_be_visible(timeout=15000)
                    expect(page.locator('#job-title')).to_have_text('Tu pack está listo')
                    expect(page.locator('#job-percentage')).to_have_text('100 %')
                    expect(page.locator('#result-retry')).to_be_visible()
                    expect(page.locator('#download')).to_be_visible()
                    page.locator('#result-retry').click()
                    with page.expect_download() as download_info:
                        page.locator('#download').click()
                    download = download_info.value
                    assert download.suggested_filename == 'Browser pack.wastickers'
                    with zipfile.ZipFile(download.path()) as archive:
                        assert archive.read('title.txt') == b'Browser pack'
                        assert sum(name.endswith('.webp') for name in archive.namelist()) == 1
                        sticker_name = next(name for name in archive.namelist() if name.endswith('.webp'))
                        with Image.open(io.BytesIO(archive.read(sticker_name))) as sticker:
                            assert sticker.getpixel((64,256))[3] == 0
                    expect(page.locator('#result-grid .result-card')).to_have_count(1)
                    page.get_by_role('button', name='Ampliar Sticker 1').click()
                    expect(page.locator('#result-dialog')).to_be_visible()
                    expect(page.locator('#result-image')).to_have_js_property('naturalWidth', 512)
                    page.locator('#close-result').click()
                    page.screenshot(path='/tmp/stickerfast-browser/package-result.png', full_page=True)
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
                    page.get_by_role('button', name='Editar imagen').click()
                    expect(page.locator('#editor-save')).to_be_enabled()
                    page.locator('#editor-rotate').click()
                    page.locator('#editor-flip').click()
                    page.screenshot(path='/tmp/stickerfast-browser/editor-mobile.png', full_page=True)
                    page.locator('#editor-close').click()
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
                    page.get_by_role('button', name='Edit image').click()
                    expect(page.locator('#editor-title')).to_have_text('Edit your sticker')
                    expect(page.locator('#editor-save')).to_have_text('Save edits')
                    page.locator('#editor-close').click()
                    page.locator('#crop-mode').select_option('fit')
                    page.locator('#create').click()
                    expect(page.locator('#job-title')).to_have_text('Your pack is ready', timeout=15000)
                    expect(page.locator('#download')).to_have_text('Download pack ↓')
                    page.locator('#language').select_option('fr')
                    expect(page.locator('#job-title')).to_have_text('Votre pack est prêt')
                    expect(page.locator('#download')).to_have_text('Télécharger le pack ↓')
                    page.locator('#delete-job').click()
                    page.locator('#language').select_option('en')
                    page.locator('#clear').click()
                    animation = io.BytesIO()
                    frames = [Image.new('RGB', (80,80), color) for color in ('red', 'blue')]
                    frames[0].save(animation, format='WEBP', save_all=True, append_images=frames[1:], duration=[80,160])
                    page.locator('#files').set_input_files({'name':'animated.webp', 'mimeType':'image/webp', 'buffer':animation.getvalue()})
                    page.get_by_role('button', name='Edit image').click()
                    expect(page.locator('#message')).to_contain_text('Your file keeps its animation.')
                    expect(page.locator('#image-editor')).to_be_hidden()
                    page.locator('#animated').check()
                    page.locator('#create').click()
                    expect(page.locator('#result-grid .result-card')).to_have_count(1, timeout=15000)
                    expect(page.locator('#result-grid')).to_contain_text('2 frames')
                    page.locator('#delete-job').click()
                    # ZIP import, accessible ordering, drag ordering, and batching.
                    page.locator('#language').select_option('es')
                    page.locator('#animated').uncheck()
                    page.locator('#clear').click()
                    bad_zip=io.BytesIO()
                    with zipfile.ZipFile(bad_zip, 'w') as archive:
                        archive.writestr('../escape.png', png('red'))
                    page.locator('#files').set_input_files({'name':'unsafe.zip','mimeType':'application/zip','buffer':bad_zip.getvalue()})
                    expect(page.locator('#message')).to_contain_text('rutas no permitidas')
                    expect(page.locator('#media-grid .media-card')).to_have_count(0)
                    collection=io.BytesIO()
                    with zipfile.ZipFile(collection, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                        for index in range(31):
                            archive.writestr(f'set/{31-index:02d}.png', png('red' if index==0 else 'blue' if index==1 else 'green'))
                        archive.writestr('notes.txt', 'ignored')
                    page.set_viewport_size({'width':1440,'height':1100})
                    page.locator('#files').set_input_files({'name':'photos.zip','mimeType':'application/zip','buffer':collection.getvalue()})
                    expect(page.locator('#media-grid .media-card')).to_have_count(31, timeout=30000)
                    expect(page.locator('#count')).to_have_text('31 / 300')
                    expect(page.locator('#split-summary')).to_contain_text('2 paquetes')
                    page.get_by_role('button', name='Subir photos/set/30.png', exact=True).click()
                    expect(page.locator('#media-grid .media-meta label span').first).to_have_text('photos/set/30.png')
                    page.locator('#media-grid .media-card').nth(0).drag_to(page.locator('#media-grid .media-card').nth(2))
                    expect(page.locator('#media-grid .media-meta label span').nth(2)).to_have_text('photos/set/30.png')
                    page.locator('#sort-files').select_option('name')
                    expect(page.locator('#media-grid .media-meta label span').first).to_have_text('photos/set/01.png')
                    page.locator('#name').fill('Large collection')
                    page.locator('#create').click()
                    expect(page.locator('#job-title')).to_have_text('Tu colección está lista', timeout=30000)
                    expect(page.locator('#download')).to_have_text('Descargar colección ZIP')
                    expect(page.locator('#result-grid .result-card')).to_have_count(31, timeout=15000)
                    with page.expect_download() as download_info:
                        page.locator('#download').click()
                    assert download_info.value.suggested_filename=='Large collection.zip'
                    with zipfile.ZipFile(download_info.value.path()) as bundle:
                        assert len(bundle.namelist())==2
                        with zipfile.ZipFile(io.BytesIO(bundle.read(bundle.namelist()[1]))) as pack:
                            sticker=next(name for name in pack.namelist() if name.endswith('.webp'))
                            with Image.open(io.BytesIO(pack.read(sticker))) as image:
                                assert image.getpixel((256,256))[0]>200
                    # Keep the first result while a second collection is generated.
                    page.locator('#clear').click()
                    page.locator('#files').set_input_files({'name':'next.png','mimeType':'image/png','buffer':png('blue')})
                    page.locator('#name').fill('Next collection')
                    page.locator('#create').click()
                    expect(page.locator('#job-title')).to_have_text('Tu pack está listo', timeout=15000)
                    page.locator('#queue-refresh').click()
                    expect(page.locator('#queue-list .queue-row')).to_have_count(2)
                    row=page.locator('#queue-list .queue-row').filter(has_text='Large collection')
                    expect(row.locator('.queue-packs a')).to_have_count(2)
                    row.get_by_role('button',name='Ver estado').click()
                    expect(page.locator('#download')).to_have_text('Descargar colección ZIP')
                    page.screenshot(path='/tmp/stickerfast-browser/large-collection.png',full_page=True)
                    page.locator('#delete-job').click()
                    page.locator('#queue-refresh').click()
                    row=page.locator('#queue-list .queue-row').filter(has_text='Next collection')
                    row.get_by_role('button',name='Ver estado').click()
                    expect(page.locator('#download')).to_have_text('Descargar pack ↓')
                    page.locator('#delete-job').click()
                    assert not errors, errors
                    print('PASS: ZIP/multiple files, ordering/drag/sort, automatic packs, retained queue results, editing/previews, both formats, six languages; no JS errors')
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
