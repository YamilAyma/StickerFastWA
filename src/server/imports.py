"""Bounded ZIP staging. Archive paths are never used as filesystem destinations."""
from pathlib import Path, PurePosixPath
import shutil
import stat
import time
import uuid
import zipfile
from threading import Lock

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

MAX_FILES = 300
MAX_TOTAL = 250 * 1024 * 1024
MAX_ZIP = 100 * 1024 * 1024
MAX_MEMBER = 25 * 1024 * 1024
MEDIA = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp4', '.webm', '.mov', '.avi', '.mkv'}


def unpack(source: Path, target: Path):
    files, ignored, total = [], 0, 0
    try:
        with zipfile.ZipFile(source) as archive:
            if len(archive.infolist()) > 2000:
                raise ValueError('El ZIP contiene demasiadas entradas.')
            for entry in archive.infolist():
                name = entry.filename
                path = PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or stat.S_ISLNK(entry.external_attr >> 16):
                    raise ValueError('El ZIP contiene rutas no permitidas.')
                if entry.flag_bits & 1:
                    raise ValueError('No se admiten ZIP cifrados.')
                if entry.is_dir():
                    continue
                if path.suffix.lower() not in MEDIA or '__MACOSX' in path.parts or path.name.startswith('._'):
                    ignored += 1
                    continue
                total += entry.file_size
                if len(files) >= MAX_FILES or entry.file_size > MAX_MEMBER or total > MAX_TOTAL:
                    raise ValueError('La colección supera los límites de archivos o tamaño.')
                destination = target / f'{len(files):04d}{path.suffix.lower()}'
                written = 0
                with archive.open(entry) as member, destination.open('wb') as output:
                    while chunk := member.read(1024 * 1024):
                        written += len(chunk)
                        if written > MAX_MEMBER or total - entry.file_size + written > MAX_TOTAL:
                            raise ValueError('La colección supera los límites de archivos o tamaño.')
                        output.write(chunk)
                if not written:
                    raise ValueError('Archivo vacío.')
                files.append({'name': name, 'size': written, 'path': destination})
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, ValueError) as error:
        raise HTTPException(422, str(error) if isinstance(error, ValueError) else 'ZIP no válido.') from error
    if not files:
        raise HTTPException(422, 'El ZIP no contiene archivos multimedia compatibles.')
    return files, ignored


def import_router(root: Path):
    router = APIRouter(prefix='/api/imports')
    staged = {}
    lock = Lock()

    @router.post('', status_code=201)
    def import_zip(file: UploadFile = File()):
        with lock:
            for key, item in list(staged.items()):
                if time.monotonic() - item['created'] > 1800:
                    shutil.rmtree(item['directory'], ignore_errors=True)
                    del staged[key]
            if len(staged) >= 8:
                raise HTTPException(429, 'Demasiadas importaciones pendientes.')
            key = uuid.uuid4().hex
            directory = root / f'import-{key}'
            directory.mkdir()
            staged[key] = dict(directory=directory, created=time.monotonic(), files=[])
        try:
            size = 0
            with (directory / 'source.zip').open('wb') as output:
                while chunk := file.file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_ZIP:
                        raise HTTPException(413, 'El ZIP supera los 100 MB.')
                    output.write(chunk)
            files, ignored = unpack(directory / 'source.zip', directory)
            (directory / 'source.zip').unlink()
            with lock:
                staged[key]['files'] = files
            return {'id': key, 'ignored': ignored, 'files': [dict(name=item['name'], size=item['size'], url=f'/api/imports/{key}/{index}') for index, item in enumerate(files)]}
        except BaseException:
            with lock:
                staged.pop(key, None)
            shutil.rmtree(directory, ignore_errors=True)
            raise
        finally:
            file.file.close()

    @router.get('/{key}/{index}')
    def get_file(key: str, index: int):
        with lock:
            item = staged.get(key)
            if not item or index < 0 or index >= len(item['files']):
                raise HTTPException(404, 'Archivo no encontrado.')
            content = item['files'][index]['path'].read_bytes()
        return Response(content, media_type='application/octet-stream', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})

    @router.delete('/{key}', status_code=204)
    def delete_import(key: str):
        with lock:
            item = staged.pop(key, None)
            if item:
                shutil.rmtree(item['directory'], ignore_errors=True)
    return router
