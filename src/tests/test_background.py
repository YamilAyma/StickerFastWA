import io
from pathlib import Path
import sys

from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.app import create_app
from server import background


def png(alpha=255):
    output=io.BytesIO()
    Image.new('RGBA',(64,64),(255,0,0,alpha)).save(output,'PNG')
    return output.getvalue()


def test_background_removal_preserves_transparency(tmp_path, monkeypatch):
    monkeypatch.setattr(background,'segment',lambda image:Image.new('RGBA',image.size,(255,0,0,128)))
    with TestClient(create_app(tmp_path)) as client:
        response=client.post('/api/remove-background',files={'file':('a.png',png(128))})
        assert response.status_code==200
        assert response.headers['cache-control']=='no-store'
        with Image.open(io.BytesIO(response.content)) as image:
            assert image.size==(64,64) and image.getpixel((32,32))[3]==64
        assert client.post('/api/remove-background',files={'file':('a.png',b'invalid')}).status_code==422


def test_model_failure_is_recoverable(tmp_path, monkeypatch):
    def fail(image):raise RuntimeError('model offline')
    monkeypatch.setattr(background,'segment',fail)
    with TestClient(create_app(tmp_path)) as client:
        assert client.post('/api/remove-background',files={'file':('a.png',png())}).status_code==503
        monkeypatch.setattr(background,'segment',lambda image:image)
        assert client.post('/api/remove-background',files={'file':('a.png',png())}).status_code==200


def test_background_busy_and_body_limit(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        background._lock.acquire()
        try:
            assert client.post('/api/remove-background',files={'file':('a.png',png())}).status_code==429
        finally:background._lock.release()
        assert client.post('/api/remove-background',content=b'',headers={'Content-Length':str(27*1024*1024)}).status_code==413
