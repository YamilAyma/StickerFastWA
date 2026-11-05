import importlib.util
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('sticker_launcher', ROOT / 'start_web.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
sys.path.insert(0, str(ROOT / 'src'))
from server.app import create_app


def test_local_default_blocks_lan_hosts(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.get('/api/launch-info').json()['lan'] is False
        assert client.get('/api/health', headers={'host': '192.168.1.25:8000'}).status_code == 400


def test_lan_host_and_same_origin_requests(tmp_path):
    with TestClient(create_app(tmp_path, lan_hosts=('192.168.1.25',)), base_url='http://192.168.1.25:8000') as client:
        assert client.get('/api/health').status_code == 200
        assert client.get('/api/launch-info').json() == {'app':'StickerFastWA','lan':True,'urls':['http://192.168.1.25:8000']}
        # 422 comes from the form validation; same-origin is allowed through.
        assert client.post('/api/jobs', headers={'origin':'http://192.168.1.25:8000'}).status_code == 422
        assert client.post('/api/jobs', headers={'origin':'https://other.example'}).status_code == 403
        assert client.get('/api/health', headers={'host':'other.example'}).status_code == 400


@pytest.mark.parametrize('host', ['*','8.8.8.8','0.0.0.0','224.0.0.1','example.com'])
def test_lan_hosts_must_be_specific_private_ips(tmp_path, host):
    with pytest.raises(ValueError):
        create_app(tmp_path, lan_hosts=(host,))


def test_launcher_reuses_same_mode(monkeypatch):
    monkeypatch.setattr(launcher, 'server_info', lambda port: {'app':'StickerFastWA','lan':True})
    assert launcher.choose_port(8000, True) == (8000, True)


def test_launcher_does_not_reinstall_unchanged_dependencies(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    (tmp_path / 'requirements-web.txt').write_text('fastapi')
    python = tmp_path / 'venv' / ('Scripts/python.exe' if launcher.os.name == 'nt' else 'bin/python')
    python.parent.mkdir(parents=True)
    python.touch()
    calls=[]
    class Result:
        returncode=0
    def run(command, **kwargs):
        calls.append(command)
        return Result()
    monkeypatch.setattr(launcher.subprocess, 'run', run)
    launcher.prepare_python()
    launcher.prepare_python()
    assert sum('install' in command for command in calls) == 1
    (tmp_path / 'requirements-web.txt').write_text('fastapi\nuvicorn')
    launcher.prepare_python()
    assert sum('install' in command for command in calls) == 2


def test_launcher_finds_existing_server_after_a_port_becomes_free(monkeypatch):
    monkeypatch.setattr(launcher, 'server_info', lambda port: {'app':'StickerFastWA','lan':False} if port == 8003 else None)
    assert launcher.choose_port(8000, False) == (8003, True)
