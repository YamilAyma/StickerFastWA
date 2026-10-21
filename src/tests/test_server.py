import io
from pathlib import Path
import sys
from threading import Event
import time
import zipfile

from PIL import Image
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.app import create_app


def picture(color='red'):
    output = io.BytesIO()
    Image.new('RGB', (80, 100), color).save(output, 'PNG')
    return output.getvalue()


def wait_for_job(client, job_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = client.get(f'/api/jobs/{job_id}')
        assert response.status_code == 200
        job = response.json()
        if job['status'] in {'completed', 'failed', 'cancelled'}:
            return job
        time.sleep(.01)
    pytest.fail('Job did not finish')


@pytest.mark.parametrize('package,extension', [('stickerMaker', 'wastickers'), ('wemoji', 'wemojipack')])
def test_upload_download_and_delete(tmp_path, package, extension):
    with TestClient(create_app(tmp_path)) as client:
        response = client.post('/api/jobs', data={'name': 'Mi paquete', 'author': 'Test', 'package': package},
                               files=[('files', ('../../first.png', picture())),
                                      ('files', ('second.png', picture('blue')))])
        assert response.status_code == 202, response.text
        job_id = response.json()['id']
        job = wait_for_job(client, job_id)
        assert job['status'] == 'completed', job
        assert job['progress'] == 100
        result = client.get(job['download_url'])
        assert result.status_code == 200
        assert extension in result.headers['content-disposition']
        with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
            assert archive.testzip() is None
            assert len([n for n in archive.namelist() if n.endswith('.webp')]) == 2
        assert not list(tmp_path.rglob('inputs'))
        assert client.delete(f'/api/jobs/{job_id}').status_code == 204
        assert client.get(f'/api/jobs/{job_id}').status_code == 404
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('name,filename,content', [('../escape', 'a.png', picture()),
                                                 ('valid', 'script.html', b'<html>'),
                                                 ('valid', 'fake.png', b'not an image')])
def test_invalid_uploads(tmp_path, name, filename, content):
    with TestClient(create_app(tmp_path)) as client:
        response = client.post('/api/jobs', data={'name': name, 'author': 'Test'},
                               files={'files': (filename, content)})
        assert response.status_code == 422
        assert not list(tmp_path.rglob('inputs'))


def test_file_limit_and_local_origin(tmp_path, monkeypatch):
    import server.app as module
    monkeypatch.setattr(module, 'MAX_FILE_BYTES', 10)
    with TestClient(create_app(tmp_path)) as client:
        assert client.get('/api/health').json() == {'status': 'ok'}
        assert client.get('/api/health', headers={'host': 'evil.example'}).status_code == 400
        response = client.post('/api/jobs', data={'name': 'Test', 'author': 'Test'},
                               files={'files': ('a.png', picture())}, headers={'origin': 'https://evil.example'})
        assert response.status_code == 403
        response = client.post('/api/jobs', data={'name': 'Test', 'author': 'Test'},
                               files={'files': ('a.png', picture())})
        assert response.status_code == 413


def test_cancellation_and_unavailable_download(tmp_path):
    entered = Event()
    release = Event()

    class BlockingEngine:
        def create_pack(self, options, progress_callback):
            entered.set()
            assert release.wait(5)
            return False

        def cancel_processing(self):
            release.set()

    with TestClient(create_app(tmp_path, engine_factory=BlockingEngine)) as client:
        response = client.post('/api/jobs', data={'name': 'Test', 'author': 'Test'},
                               files={'files': ('a.png', picture())})
        job_id = response.json()['id']
        assert entered.wait(5)
        assert client.get(f'/api/jobs/{job_id}/download').status_code == 409
        assert client.delete(f'/api/jobs/{job_id}').status_code == 409
        assert client.post(f'/api/jobs/{job_id}/cancel').status_code == 202
        assert wait_for_job(client, job_id)['status'] == 'cancelled'
        assert client.get(f'/api/jobs/{job_id}/download').status_code == 409
        assert client.delete(f'/api/jobs/{job_id}').status_code == 204


@pytest.mark.parametrize('extension', ['gif', 'webp', 'avi'])
def test_animated_input(tmp_path, extension):
    if extension == 'avi':
        import cv2
        import numpy as np
        source = tmp_path / 'video.avi'
        writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*'MJPG'), 12, (64, 64))
        assert writer.isOpened()
        for index in range(8):
            frame = np.zeros((64, 64, 3), dtype=np.uint8)
            frame[:, index * 4:index * 4 + 8] = (20, 200, 50)
            writer.write(frame)
        writer.release()
        content = source.read_bytes()
    else:
        output = io.BytesIO()
        frames = [Image.new('RGB', (80, 80), color) for color in ('red', 'blue', 'green')]
        frames[0].save(output, format=extension, save_all=True, append_images=frames[1:], duration=80)
        content = output.getvalue()
    with TestClient(create_app(tmp_path)) as client:
        response = client.post('/api/jobs', data={'name': 'Animated', 'author': 'Test', 'animated': 'true'},
                               files={'files': (f'animation.{extension}', content)})
        assert response.status_code == 202, response.text
        job = wait_for_job(client, response.json()['id'])
        assert job['status'] == 'completed', job
        with zipfile.ZipFile(io.BytesIO(client.get(job['download_url']).content)) as archive:
            sticker = next(n for n in archive.namelist() if n.endswith('.webp'))
            with Image.open(io.BytesIO(archive.read(sticker))) as image:
                assert image.n_frames > 1
                assert image.size == (512, 512)
            assert len(archive.read(sticker)) < 500000


def test_request_body_limit(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        response = client.post('/api/jobs', content=b'', headers={'Content-Length': str(200 * 1024 * 1024)})
        assert response.status_code == 413


def test_failed_conversion_is_not_downloadable(tmp_path):
    class FailingEngine:
        def create_pack(self, options, progress_callback):
            return False

        def cancel_processing(self):
            pass

    with TestClient(create_app(tmp_path, engine_factory=FailingEngine)) as client:
        response = client.post('/api/jobs', data={'name': 'Test', 'author': 'Test'},
                               files={'files': ('a.png', picture())})
        job_id = response.json()['id']
        job = wait_for_job(client, job_id)
        assert job['status'] == 'failed'
        assert job['error']
        assert job['download_url'] is None
        assert not list(tmp_path.rglob('inputs'))
        assert client.get(f'/api/jobs/{job_id}/download').status_code == 409


def test_custom_icon_does_not_become_a_sticker(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        response = client.post('/api/jobs', data={'name': 'Icon', 'author': 'Test'},
                               files=[('files', ('image.png', picture())), ('icon', ('icon.png', picture('green')))])
        assert response.status_code == 202, response.text
        job = wait_for_job(client, response.json()['id'])
        assert job['status'] == 'completed'
        with zipfile.ZipFile(io.BytesIO(client.get(job['download_url']).content)) as archive:
            assert sum(name.endswith('.webp') for name in archive.namelist()) == 1
            with Image.open(io.BytesIO(archive.read('tray_icon.png'))) as icon:
                assert icon.size == (96, 96)
                assert icon.getpixel((48, 48))[:3] == (0, 128, 0)


def test_web_interface_and_assets_are_served(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        page = client.get('/')
        assert page.status_code == 200
        assert 'text/html' in page.headers['content-type']
        assert 'id="pack-form"' in page.text
        assert client.get('/web/app.js').status_code == 200
        assert client.get('/web/style.css').status_code == 200
        assert client.get('/web/../app.py').status_code == 404
        response = client.post('/api/jobs', data={'name': 'Test', 'author': 'Test'},
                               files={'files': ('fake.png', b'invalid')})
        assert response.status_code == 422
        assert str(tmp_path) not in response.text
