"""One-click local launcher. Python 3.10+ is the only bootstrap prerequisite."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import venv
import webbrowser

ROOT = Path(__file__).resolve().parent


def lan_addresses():
    addresses = set()
    try:
        addresses.update(info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    # UDP connect selects the local interface without sending a packet.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(('192.168.255.254', 9))
            addresses.add(probe.getsockname()[0])
    except OSError:
        pass
    return sorted(address for address in addresses if ipaddress.ip_address(address).is_private
                  and not ipaddress.ip_address(address).is_loopback)


def prepare_python():
    folder = ROOT / 'venv'
    python = folder / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        print('Preparando Python para StickerFast WA…', flush=True)
        venv.EnvBuilder(with_pip=True).create(folder)
    requirements = ROOT / 'requirements-web.txt'
    digest = hashlib.sha256(requirements.read_bytes() + sys.version.encode()).hexdigest()
    stamp = folder / '.stickerfast-web-ready'
    if not stamp.exists() or stamp.read_text() != digest:
        print('Instalando dependencias web. La primera vez puede tardar unos minutos…', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(requirements)], check=True, cwd=ROOT)
        stamp.write_text(digest)
    check = subprocess.run([str(python), '-c', 'import fastapi, uvicorn, multipart, PIL, numpy, webp, munch, cv2, rembg, onnxruntime'], capture_output=True)
    if check.returncode:
        stamp.unlink(missing_ok=True)
        raise RuntimeError('Las dependencias no están completas. Vuelve a ejecutar el lanzador para repararlas.')
    return python


def server_info(port):
    try:
        # Local readiness never goes through an outbound HTTP proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{port}/api/launch-info', timeout=.5) as response:
            data = json.load(response)
            return data if data.get('app') == 'StickerFastWA' else None
    except (OSError, ValueError):
        return None


def choose_port(preferred, lan):
    ports = range(preferred, min(preferred + 10, 65536))
    for port in ports:
        info = server_info(port)
        if info is not None and info.get('lan') == lan:
            return port, True
    for port in ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(('0.0.0.0' if lan else '127.0.0.1', port))
                return port, False
        except OSError:
            pass
    raise RuntimeError('No hay un puerto libre. Cierra otra instancia o indica --port.')


def main():
    if sys.version_info < (3, 10):
        raise RuntimeError('Instala Python 3.10 o posterior para continuar.')
    parser = argparse.ArgumentParser(description='Inicia StickerFast WA y abre el navegador.')
    parser.add_argument('--lan', action='store_true', help='Permitir acceso desde la misma red local.')
    parser.add_argument('--no-browser', action='store_true', help='No abrir el navegador automáticamente.')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('El puerto debe estar entre 1 y 65535.')
    port, reuse = choose_port(args.port, args.lan)
    url = f'http://127.0.0.1:{port}'
    if reuse:
        print(f'StickerFast WA ya está funcionando: {url}', flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        return
    python = prepare_python()
    addresses = lan_addresses() if args.lan else []
    if args.lan and not addresses:
        raise RuntimeError('No se encontró una dirección de red local. Conéctate a Wi-Fi o usa el inicio local.')
    environment = dict(os.environ, STICKERFAST_LAN_HOSTS=','.join(addresses))
    process = subprocess.Popen([str(python), '-m', 'uvicorn', 'server.app:app', '--app-dir', str(ROOT / 'src'),
                                '--host', '0.0.0.0' if args.lan else '127.0.0.1', '--port', str(port)], cwd=ROOT, env=environment)
    try:
        for _ in range(200):
            if process.poll() is not None:
                raise RuntimeError('El servidor no pudo arrancar. Revisa el mensaje de error anterior.')
            if server_info(port):
                break
            time.sleep(.1)
        else:
            raise RuntimeError('El servidor no respondió a tiempo.')
        print(f'\nStickerFast WA: {url}', flush=True)
        for address in addresses:
            print(f'Teléfono (misma red Wi-Fi): http://{address}:{port}', flush=True)
        if addresses:
            print('Usa una red de confianza. Si el teléfono no conecta, permite Python en el firewall de la red privada.', flush=True)
        print('Mantén esta ventana abierta. Ctrl+C detiene el servidor.', flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'\nNo se pudo iniciar StickerFast WA: {error}', file=sys.stderr)
        sys.exit(1)
