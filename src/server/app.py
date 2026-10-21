"""Local server. Run: uvicorn server.app:app --app-dir src --host 127.0.0.1."""
from concurrent.futures import ThreadPoolExecutor
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, Lock
from typing import Annotated, Literal
import shutil
import tempfile
import time
import uuid
import zipfile

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from PIL import Image

from logic.engine import StickerEngine

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_JOB_BYTES = 100 * 1024 * 1024
MAX_JOBS = 16
RETENTION_SECONDS = 3600
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
VIDEO_EXTENSIONS = {'.mp4', '.webm', '.mov', '.avi', '.mkv'}
TERMINAL = {'completed', 'failed', 'cancelled'}


class UploadLimitMiddleware:
    """Bound the multipart body before it can fill temporary upload storage."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'] != '/api/jobs' or scope['method'] != 'POST':
            return await self.app(scope, receive, send)
        limit = MAX_JOB_BYTES + 1024 * 1024  # Allow multipart metadata overhead.
        headers = dict(scope['headers'])
        try:
            length = int(headers.get(b'content-length', b'0'))
        except ValueError:
            return await JSONResponse({'detail': 'Content-Length inválido.'}, 400)(scope, receive, send)
        if length > limit:
            return await JSONResponse({'detail': 'Carga demasiado grande.'}, 413)(scope, receive, send)
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get('body', b''))
            if consumed > limit:
                raise HTTPException(413, 'Carga demasiado grande.')
            return message

        return await self.app(scope, bounded_receive, send)


@dataclass
class Job:
    id: str
    directory: Path
    engine: StickerEngine = field(default_factory=StickerEngine)
    cancel: Event = field(default_factory=Event)
    status: str = 'queued'
    current: int = 0
    total: int = 0
    error: str | None = None
    result: Path | None = None
    finished: float | None = None


def validate_name(value: str) -> str:
    value = value.strip()
    if not value or len(value) > 80 or value in {'.', '..'} or any(
        char in '/\\:*?"<>|' or ord(char) < 32 for char in value
    ):
        raise HTTPException(422, 'Nombre de paquete inválido (máximo 80 caracteres, sin separadores).')
    return value


def validate_media(path: Path, animated: bool, icon: bool = False):
    try:
        if path.suffix in VIDEO_EXTENSIONS:
            if icon or not animated:
                raise ValueError('Los videos requieren modo animado y no pueden usarse como icono.')
            import cv2
            capture = cv2.VideoCapture(str(path))
            try:
                ok, frame = capture.read()
                if not ok or frame is None:
                    raise ValueError('No se puede leer el video.')
            finally:
                capture.release()
        else:
            with Image.open(path) as image:
                if image.width * image.height > 25_000_000:
                    raise ValueError('Imagen demasiado grande (máximo 25 megapíxeles).')
                if not icon and animated and path.suffix not in {'.gif', '.webp'}:
                    raise ValueError('El modo animado admite GIF, WebP y videos.')
                if not icon and not animated and getattr(image, 'n_frames', 1) > 1:
                    raise ValueError('Activa el modo animado para archivos animados.')
                image.verify()
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except (OSError, Image.DecompressionBombError) as error:
        raise HTTPException(422, 'No se pudo leer el archivo. Comprueba que sea una imagen o un video válido.') from error


def create_app(data_dir: Path | None = None, *, engine_factory=StickerEngine) -> FastAPI:
    jobs: dict[str, Job] = {}
    lock = Lock()
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='sticker-job')
    root = Path(tempfile.mkdtemp(prefix='stickerfast-web-', dir=data_dir))

    @asynccontextmanager
    async def lifespan(app):
        yield
        with lock:
            for job in jobs.values():
                job.cancel.set()
                job.engine.cancel_processing()
        pool.shutdown(wait=True, cancel_futures=True)
        shutil.rmtree(root, ignore_errors=True)

    app = FastAPI(title='StickerFastWA Local', version='0.1.0', lifespan=lifespan)
    web_dir = Path(__file__).resolve().parent / 'web'
    app.mount('/web', StaticFiles(directory=web_dir), name='web')
    app.add_middleware(UploadLimitMiddleware)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])

    @app.middleware('http')
    async def local_origin(request: Request, call_next):
        origin = request.headers.get('origin')
        expected = f'{request.url.scheme}://{request.headers.get("host", "")}'
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and origin and origin != expected:
            return JSONResponse({'detail': 'Origen no permitido.'}, status_code=403)
        return await call_next(request)

    def lookup(job_id):
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, 'Trabajo no encontrado.')
        return job

    def cleanup():
        # Called under lock. Downloads are served from memory below to avoid deletion races.
        for job_id, job in list(jobs.items()):
            if job.finished is not None and time.monotonic() - job.finished > RETENTION_SECONDS:
                shutil.rmtree(job.directory, ignore_errors=True)
                del jobs[job_id]

    def run(job, options):
        result = None
        try:
            with lock:
                if job.cancel.is_set():
                    return
                job.status = 'running'

            def progress(current, total):
                with lock:
                    job.current = min(current, job.total)
                if job.cancel.is_set():
                    job.engine.cancel_processing()

            success = job.engine.create_pack(options, progress_callback=progress)
            extension = 'wastickers' if options['package'] == 'stickerMaker' else 'wemojipack'
            archive = Path(options['directory']) / f'{options["namepack"]}.{extension}'
            if not job.cancel.is_set():
                if not success or not archive.is_file():
                    raise RuntimeError('No se pudo generar el paquete.')
                with zipfile.ZipFile(archive) as output:
                    if output.testzip() is not None or sum(n.endswith('.webp') for n in output.namelist()) != job.total:
                        raise RuntimeError('La conversión no produjo todos los stickers esperados.')
                destination = job.directory / archive.name
                archive.replace(destination)
                result = destination
        except Exception:
            with lock:
                job.error = 'No se pudo convertir el contenido del paquete.'
        finally:
            shutil.rmtree(job.directory / 'inputs', ignore_errors=True)
            (job.directory / 'icon.png').unlink(missing_ok=True)
            with lock:
                if job.cancel.is_set():
                    job.status = 'cancelled'
                    if result:
                        result.unlink(missing_ok=True)
                elif result is not None:
                    job.result = result
                    job.current = job.total
                    job.status = 'completed'
                else:
                    job.status = 'failed'
                job.finished = time.monotonic()

    @app.get('/', include_in_schema=False)
    def index():
        return FileResponse(web_dir / 'index.html')

    @app.get('/api/health')
    def health():
        return {'status': 'ok'}

    @app.post('/api/jobs', status_code=202)
    async def create_job(
        files: Annotated[list[UploadFile], File()],
        name: Annotated[str, Form()],
        author: Annotated[str, Form(min_length=1, max_length=80)],
        package: Annotated[Literal['stickerMaker', 'wemoji'], Form()] = 'stickerMaker',
        animated: Annotated[bool, Form()] = False,
        crop_mode: Annotated[Literal['center_crop', 'fit'], Form()] = 'center_crop',
        icon: Annotated[UploadFile | None, File()] = None,
    ):
        name = validate_name(name)
        if not author.strip():
            raise HTTPException(422, 'El autor es obligatorio.')
        if not 1 <= len(files) <= 30:
            raise HTTPException(422, 'Selecciona entre 1 y 30 archivos.')
        with lock:
            cleanup()
            if len(jobs) >= MAX_JOBS:
                raise HTTPException(429, 'Demasiados trabajos. Elimina alguno o espera a que expire.')
            job_id = uuid.uuid4().hex
            directory = root / job_id
            directory.mkdir()
            inputs = directory / 'inputs'
            inputs.mkdir()
            job = Job(job_id, directory, engine=engine_factory(), total=len(files), status='uploading')
            jobs[job_id] = job
        total_bytes = 0

        async def save(upload, destination):
            nonlocal total_bytes
            size = 0
            with destination.open('wb') as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    total_bytes += len(chunk)
                    if size > MAX_FILE_BYTES or total_bytes > MAX_JOB_BYTES:
                        raise HTTPException(413, 'Máximo 25 MB por archivo y 100 MB por trabajo.')
                    output.write(chunk)
            if size == 0:
                raise HTTPException(422, 'Archivo vacío.')

        try:
            for index, upload in enumerate(files):
                suffix = Path(upload.filename or '').suffix.lower()
                if suffix not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                    raise HTTPException(422, 'Formato no admitido.')
                target = inputs / f'{index:02d}{suffix}'
                await save(upload, target)
                await asyncio.to_thread(validate_media, target, animated)
            icon_path = directory / 'icon.png'
            if icon:
                suffix = Path(icon.filename or '').suffix.lower()
                if suffix not in IMAGE_EXTENSIONS:
                    raise HTTPException(422, 'El icono debe ser una imagen.')
                uploaded_icon = directory / f'uploaded-icon{suffix}'
                await save(icon, uploaded_icon)
                await asyncio.to_thread(validate_media, uploaded_icon, animated, icon=True)
                with Image.open(uploaded_icon) as image:
                    image.convert('RGBA').save(icon_path)
                uploaded_icon.unlink()
            else:
                first = sorted(inputs.iterdir())[0]
                if first.suffix in VIDEO_EXTENSIONS:
                    import cv2
                    capture = cv2.VideoCapture(str(first))
                    try:
                        ok, frame = capture.read()
                        if not ok:
                            raise HTTPException(422, 'No se pudo crear el icono.')
                        Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).save(icon_path)
                    finally:
                        capture.release()
                else:
                    with Image.open(first) as image:
                        image.convert('RGBA').save(icon_path)
            options = dict(package=package, animated=animated, namepack=name, author=author.strip(),
                           directory=str(inputs), icon=str(icon_path), conserve=True, crop_mode=crop_mode)
            with lock:
                job.status = 'queued'
            pool.submit(run, job, options)
            return {'id': job.id, 'status_url': f'/api/jobs/{job.id}'}
        except BaseException:
            with lock:
                jobs.pop(job.id, None)
            shutil.rmtree(directory, ignore_errors=True)
            raise
        finally:
            for upload in files + ([icon] if icon else []):
                await upload.close()

    @app.get('/api/jobs/{job_id}')
    def get_job(job_id: str):
        with lock:
            job = lookup(job_id)
            return {'id': job.id, 'status': job.status, 'current': job.current, 'total': job.total,
                    'progress': 100 if job.status == 'completed' else min(99, int(job.current / job.total * 100)),
                    'error': job.error,
                    'download_url': f'/api/jobs/{job.id}/download' if job.status == 'completed' else None}

    @app.post('/api/jobs/{job_id}/cancel', status_code=202)
    def cancel_job(job_id: str):
        with lock:
            job = lookup(job_id)
            if job.status in TERMINAL:
                raise HTTPException(409, 'El trabajo ya terminó.')
            job.cancel.set()
            job.engine.cancel_processing()
            return {'id': job.id, 'status': 'cancelling'}

    @app.get('/api/jobs/{job_id}/download')
    def download(job_id: str):
        from fastapi.responses import Response
        with lock:
            job = lookup(job_id)
            if job.status != 'completed' or job.result is None:
                raise HTTPException(409, 'El paquete aún no está disponible.')
            content = job.result.read_bytes()
            from urllib.parse import quote
            filename = quote(job.result.name, safe='')
        return Response(content, media_type='application/zip',
                        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{filename}"})

    @app.delete('/api/jobs/{job_id}', status_code=204)
    def delete_job(job_id: str):
        with lock:
            job = lookup(job_id)
            if job.status not in TERMINAL:
                raise HTTPException(409, 'Cancela el trabajo y espera a que termine antes de eliminarlo.')
            shutil.rmtree(job.directory, ignore_errors=True)
            del jobs[job_id]

    return app


app = create_app()
