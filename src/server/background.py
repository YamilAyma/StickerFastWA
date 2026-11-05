"""On-device background segmentation. Downloads the verified small model once."""
from io import BytesIO
import os
from pathlib import Path
import sys
from threading import Lock

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageChops

_lock = Lock()
_session = None


def segment(image):
    global _session
    os.environ.setdefault('OMP_NUM_THREADS', str(min(4, os.cpu_count() or 1)))
    from rembg import new_session, remove
    os.environ.setdefault('U2NET_HOME', str(Path(sys.prefix) / '.stickerfast-models'))
    if _session is None:
        _session = new_session('u2netp', providers=['CPUExecutionProvider'])
    return remove(image, session=_session).convert('RGBA')


def background_router():
    router = APIRouter()

    @router.post('/api/remove-background')
    def remove_background(file: UploadFile = File()):
        if not _lock.acquire(blocking=False):
            raise HTTPException(429, 'Ya se está quitando otro fondo. Inténtalo en unos segundos.')
        try:
            content = file.file.read(25 * 1024 * 1024 + 1)
            if len(content) > 25 * 1024 * 1024:
                raise HTTPException(413, 'El archivo supera los 25 MB.')
            try:
                with Image.open(BytesIO(content)) as source:
                    if source.width * source.height > 25_000_000:
                        raise ValueError('Image too large')
                    if getattr(source, 'n_frames', 1) != 1:
                        raise ValueError('Animation not supported')
                    image = source.convert('RGBA')
            except (OSError, ValueError, Image.DecompressionBombError) as error:
                raise HTTPException(422, 'Selecciona una imagen estática válida de hasta 25 megapíxeles.') from error
            try:
                result = segment(image)
                # Removal may only reduce alpha, never bring back erased areas.
                result.putalpha(ImageChops.multiply(image.getchannel('A'), result.getchannel('A')))
                output = BytesIO()
                result.save(output, format='PNG')
                return Response(output.getvalue(), media_type='image/png', headers={'Cache-Control':'no-store'})
            except Exception as error:
                raise HTTPException(503, 'No se pudo quitar el fondo. La primera vez se necesita Internet para descargar el modelo.') from error
        finally:
            file.file.close()
            _lock.release()

    return router
