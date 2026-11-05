import io
from pathlib import Path
import stat
import sys
from threading import Event
import zipfile

from fastapi.testclient import TestClient
from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.app import create_app
from logic.engine import StickerEngine
from .test_server import picture, wait_for_job


def zip_files(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return output.getvalue()


def test_import_nested_zip_and_cleanup(tmp_path):
    payload = picture()
    with TestClient(create_app(tmp_path)) as client:
        response = client.post('/api/imports', files={'file': ('photos.zip', zip_files([('folder/a.png', payload), ('notes.txt', b'ignored')]))})
        assert response.status_code == 201, response.text
        data = response.json()
        assert data['ignored'] == 1
        assert data['files'][0]['name'] == 'folder/a.png'
        assert client.get(data['files'][0]['url']).content == payload
        assert client.delete(f'/api/imports/{data["id"]}').status_code == 204
        assert client.get(data['files'][0]['url']).status_code == 404
        assert not list(tmp_path.rglob('import-*'))


@pytest.mark.parametrize('name', ['../escape.png', '/absolute.png', 'C:\\escape.png', 'nested/../../escape.png'])
def test_reject_unsafe_zip_paths(tmp_path, name):
    with TestClient(create_app(tmp_path)) as client:
        response = client.post('/api/imports', files={'file': ('bad.zip', zip_files([(name, picture())]))})
        assert response.status_code == 422
        assert not list(tmp_path.rglob('import-*'))


def test_zip_symlinks_and_expansion_limit(tmp_path, monkeypatch):
    import server.imports as imports
    link = zipfile.ZipInfo('link.png')
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with TestClient(create_app(tmp_path)) as client:
        assert client.post('/api/imports', files={'file': ('bad.zip', zip_files([(link, b'/etc/passwd')]))}).status_code == 422
        monkeypatch.setattr(imports, 'MAX_MEMBER', 10)
        assert client.post('/api/imports', files={'file': ('big.zip', zip_files([('a.png', b'a' * 11)]))}).status_code == 422
        assert client.post('/api/imports', files={'file': ('bad.zip', b'not a zip')}).status_code == 422
        assert not list(tmp_path.rglob('import-*'))


def collection_files(count=31):
    files = []
    for index in range(count):
        output = io.BytesIO()
        Image.new('RGB', (20, 20), (index * 7 % 256, 0, 0)).save(output, 'PNG')
        files.append(('files', (f'{count-index:03d}.png', output.getvalue())))
    return files


@pytest.mark.parametrize('package,extension', [('stickerMaker', 'wastickers'), ('wemoji', 'wemojipack')])
def test_collection_splits_and_keeps_explicit_order(tmp_path, package, extension):
    with TestClient(create_app(tmp_path)) as client:
        response = client.post('/api/jobs', data={'name': 'Collection', 'author': 'Test', 'package': package}, files=collection_files())
        assert response.status_code == 202, response.text
        job = wait_for_job(client, response.json()['id'])
        assert job['status'] == 'completed', job
        assert [pack['total'] for pack in job['packs']] == [30, 1]
        assert all(pack['status'] == 'completed' for pack in job['packs'])
        with zipfile.ZipFile(io.BytesIO(client.get(job['download_url']).content)) as bundle:
            assert bundle.namelist() == [f'Collection (1-2).{extension}', f'Collection (2-2).{extension}']
            colors = []
            for index, name in enumerate(bundle.namelist()):
                content = bundle.read(name)
                assert client.get(job['packs'][index]['download_url']).content == content
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    for sticker in [name for name in archive.namelist() if name.endswith('.webp')]:
                        with Image.open(io.BytesIO(archive.read(sticker))) as image:
                            colors.append(image.getpixel((256, 256))[0])
            assert len(colors) == 31
            assert all(abs(value - index * 7) < 6 for index, value in enumerate(colors))
        manifest = client.get(job['preview_url']).json()['stickers']
        assert len(manifest) == 31 and manifest[-1]['pack_index'] == 1
        assert client.get(manifest[-1]['url']).status_code == 200
        assert client.get('/api/jobs').json()['jobs'][0]['id'] == job['id']
        assert client.delete(f'/api/jobs/{job["id"]}').status_code == 204


def test_pending_queue_cancels_without_starting(tmp_path):
    release, entered = Event(), Event()
    instances = []

    class BlockingEngine:
        def __init__(self):
            self.started = False
            instances.append(self)

        def create_pack(self, options, progress_callback):
            self.started = True
            if sum(item.started for item in instances) == 2:
                entered.set()
            release.wait(10)
            return False

        def cancel_processing(self):
            pass

    with TestClient(create_app(tmp_path, engine_factory=BlockingEngine)) as client:
        try:
            ids = [client.post('/api/jobs', data={'name': str(index), 'author': 'Test'}, files={'files': ('a.png', picture())}).json()['id'] for index in range(3)]
            assert entered.wait(5)
            assert client.get(f'/api/jobs/{ids[2]}').json()['status'] == 'queued'
            assert client.post(f'/api/jobs/{ids[2]}/cancel').status_code == 202
            assert client.get(f'/api/jobs/{ids[2]}').json()['status'] == 'cancelled'
            assert not instances[2].started
            assert client.delete(f'/api/jobs/{ids[2]}').status_code == 204
        finally:
            release.set()


def test_finished_pack_survives_later_failure(tmp_path):
    class FailSecond(StickerEngine):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def create_pack(self, options, progress_callback):
            self.calls += 1
            return super().create_pack(options, progress_callback) if self.calls == 1 else False

    with TestClient(create_app(tmp_path, engine_factory=FailSecond)) as client:
        response = client.post('/api/jobs', data={'name': 'Partial', 'author': 'Test'}, files=collection_files())
        job = wait_for_job(client, response.json()['id'])
        assert job['status'] == 'failed'
        assert job['packs'][0]['status'] == 'completed'
        assert client.get(job['packs'][0]['download_url']).status_code == 200
        assert job['packs'][1]['download_url'] is None
        assert not list(tmp_path.rglob('inputs'))
