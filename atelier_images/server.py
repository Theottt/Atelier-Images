"""Local image studio. No external services or additional packages required."""
import argparse
import copy
import io
import json
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests
from PIL import Image, ImageOps

# Portable Python does not automatically include the script directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from models import DEFAULT_MODEL, list_models, model_info
from qwen_workflow import make_qwen_prompt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUTPUT = ROOT / 'ComfyUI/output'
COMFY = 'http://127.0.0.1:8188'
URL = 'http://127.0.0.1:8189'
FORMATS = {'square': (512, 512), 'portrait': (512, 768), 'landscape': (768, 512)}
LOCK = threading.RLock()
STATE = HERE / 'active_job.json'
START_ERROR = ''


def comfy_ready():
    try:
        return requests.get(COMFY + '/system_stats', timeout=2).ok
    except requests.RequestException:
        return False


def start_comfy():
    global START_ERROR
    if comfy_ready():
        return
    try:
        with (HERE / 'comfyui.log').open('ab') as log:
            process = subprocess.Popen(
                [sys.executable, '-s', str(ROOT / 'ComfyUI/main.py'), '--windows-standalone-build', '--disable-auto-launch'],
                cwd=ROOT, stdout=log, stderr=log,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        for _ in range(180):
            if comfy_ready():
                return
            if process.poll() is not None:
                raise RuntimeError('ComfyUI ne démarre pas. Consulte atelier_images/comfyui.log.')
            time.sleep(2)
        START_ERROR = 'ComfyUI met plus de temps que prévu à démarrer. Consulte atelier_images/comfyui.log.'
    except (OSError, RuntimeError) as error:
        START_ERROR = str(error)


def active_job():
    return json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else None


def job_status(job):
    if job.get('state') in ('done', 'error'):
        return job
    response = requests.get(COMFY + '/history/' + job['id'], timeout=10)
    response.raise_for_status()
    entry = response.json().get(job['id'])
    if entry:
        status = entry.get('status', {})
        if status.get('status_str') == 'error':
            errors = [data.get('exception_message', 'Erreur ComfyUI') for kind, data in status.get('messages', []) if kind == 'execution_error']
            return {**job, 'state': 'error', 'error': errors[-1] if errors else 'La génération a échoué.'}
        if status.get('completed'):
            images = [item['filename'] for out in entry.get('outputs', {}).values() for item in out.get('images', []) if item.get('type') == 'output']
            completed = {**job, 'state': 'done', 'images': images}
            with LOCK:
                latest = active_job()
                if latest and latest['id'] == job['id']:
                    temporary = STATE.with_suffix('.tmp')
                    temporary.write_text(json.dumps(completed, ensure_ascii=False), encoding='utf-8')
                    temporary.replace(STATE)
            return completed
    response = requests.get(COMFY + '/queue', timeout=10)
    response.raise_for_status()
    queue = response.json()
    for key, state in [('queue_running', 'running'), ('queue_pending', 'queued')]:
        if any(item[1] == job['id'] for item in queue.get(key, [])):
            return {**job, 'state': state}
    return {**job, 'state': 'error', 'error': 'Cette génération a été interrompue ou retirée de la file. Tu peux la relancer.'}


def make_prompt(text, shape, seed, model=None, reference=None):
    model = model or model_info(DEFAULT_MODEL)
    if model.get('family') == 'qwen21':
        width, height = FORMATS[shape]
        return make_qwen_prompt(text, width, height, seed, reference)
    workflow = json.loads((HERE / 'workflows/FLUX_Schnell_Test.json').read_text(encoding='utf-8'))
    workflow = copy.deepcopy(workflow)
    width, height = FORMATS[shape]
    by_id = {node['id']: node for node in workflow['nodes']}
    by_id[1]['widgets_values'] = [model['name']]
    by_id[3]['widgets_values'] = [text]
    by_id[5]['widgets_values'] = [width, height, 1]
    by_id[6]['widgets_values'][0] = seed
    by_id[6]['widgets_values'][2] = model['steps']
    by_id[9]['widgets_values'] = ['Atelier_FLUX']
    graph = {
        '1': {'class_type': 'UnetLoaderGGUF', 'inputs': {'unet_name': model['name']}},
        '2': {'class_type': 'DualCLIPLoader', 'inputs': {'clip_name1': 'clip_l.safetensors', 'clip_name2': 't5xxl_fp16.safetensors', 'type': 'flux', 'device': 'cpu'}},
        '3': {'class_type': 'CLIPTextEncode', 'inputs': {'text': text, 'clip': ['2', 0]}},
        '4': {'class_type': 'ConditioningZeroOut', 'inputs': {'conditioning': ['3', 0]}},
        '5': {'class_type': 'EmptySD3LatentImage', 'inputs': {'width': width, 'height': height, 'batch_size': 1}},
        '6': {'class_type': 'KSampler', 'inputs': {'model': ['1', 0], 'positive': ['3', 0], 'negative': ['4', 0], 'latent_image': ['5', 0], 'seed': seed, 'steps': model['steps'], 'cfg': 1.0, 'sampler_name': 'euler', 'scheduler': 'simple', 'denoise': 1.0}},
        '7': {'class_type': 'VAELoader', 'inputs': {'vae_name': 'ae.safetensors'}},
        '8': {'class_type': 'VAEDecode', 'inputs': {'samples': ['6', 0], 'vae': ['7', 0]}},
        '9': {'class_type': 'SaveImage', 'inputs': {'images': ['8', 0], 'filename_prefix': 'Atelier_FLUX'}},
    }
    if model['variant'] == 'dev':
        graph['10'] = {'class_type': 'FluxGuidance', 'inputs': {'conditioning': ['3', 0], 'guidance': 3.5}}
        graph['6']['inputs']['positive'] = ['10', 0]
        link = next(link for link in workflow['links'] if link[3] == 6 and link[4] == 1)
        old_id = link[0]
        by_id[3]['outputs'][0]['links'].remove(old_id)
        new_id = workflow['last_link_id'] + 1
        by_id[3]['outputs'][0]['links'].append(new_id)
        link[1], link[2] = 10, 0
        workflow['links'].append([new_id, 3, 0, 10, 0, 'CONDITIONING'])
        workflow['nodes'].append({'id': 10, 'type': 'FluxGuidance', 'pos': [460, 740], 'size': [280, 90], 'flags': {}, 'order': 9, 'mode': 0,
                                  'inputs': [{'name': 'conditioning', 'type': 'CONDITIONING', 'link': new_id}],
                                  'outputs': [{'name': 'CONDITIONING', 'type': 'CONDITIONING', 'links': [old_id], 'slot_index': 0}],
                                  'properties': {'Node name for S&R': 'FluxGuidance'}, 'widgets_values': [3.5]})
        workflow['last_node_id'], workflow['last_link_id'] = 10, new_id
    return {'prompt': graph, 'extra_data': {'extra_pnginfo': {'workflow': workflow}}}


def gallery():
    files = sorted([*OUTPUT.glob('Atelier_FLUX*.png'), *OUTPUT.glob('Atelier_Qwen*.png'), *OUTPUT.glob('FLUX_Schnell_Test*.png')], key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for path in files[:150]:
        try:
            with Image.open(path) as image:
                graph = json.loads(image.info.get('prompt', '{}'))
                result.append({'filename': path.name, 'width': image.width, 'height': image.height,
                               'prompt': graph.get('3', {}).get('inputs', {}).get('text', graph.get('3', {}).get('inputs', {}).get('prompt', '')),
                               'seed': graph.get('6', {}).get('inputs', {}).get('seed'),
                               'model': graph.get('1', {}).get('inputs', {}).get('unet_name', ''),
                               'reference': graph.get('11', {}).get('inputs', {}).get('image'),
                               'created': path.stat().st_mtime})
        except (OSError, ValueError):
            continue
    return result


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body, content_type='application/json; charset=utf-8'):
        data = json.dumps(body, ensure_ascii=False).encode() if content_type.startswith('application/json') else body
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' blob:; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def allowed(self):
        return self.headers.get('Host') in ('127.0.0.1:8189', 'localhost:8189') and self.headers.get('Origin', URL) in (URL, 'http://localhost:8189')

    def do_GET(self):
        if not self.allowed():
            return self.reply(403, {'error': 'Accès local uniquement.'})
        path = unquote(urlsplit(self.path).path)
        try:
            if path == '/api/status':
                ready = comfy_ready()
                return self.reply(200, {'app': 'atelier-images', 'ready': ready, 'error': START_ERROR if not ready else '', 'job': active_job()})
            if path == '/api/job':
                job = active_job()
                return self.reply(200, job_status(job) if job else {'state': 'idle'})
            if path == '/api/gallery':
                return self.reply(200, gallery())
            if path == '/api/models':
                return self.reply(200, list_models())
            if path.startswith('/images/'):
                filename = path[len('/images/'):]
                file = OUTPUT / filename
                if file.resolve().parent != OUTPUT.resolve() or not filename.startswith(('Atelier_FLUX', 'Atelier_Qwen', 'FLUX_Schnell_Test')) or file.suffix != '.png':
                    return self.reply(404, {'error': 'Image introuvable.'})
                return self.reply(200, file.read_bytes(), 'image/png')
            static = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if path in static:
                filename, mime = static[path]
                return self.reply(200, (HERE / 'dist' / filename).read_bytes(), mime)
            self.reply(404, {'error': 'Page introuvable.'})
        except requests.RequestException:
            self.reply(503, {'error': 'ComfyUI est indisponible. Attends son démarrage ou relance Atelier Images.'})
        except OSError:
            self.reply(404, {'error': 'Fichier introuvable.'})

    def do_POST(self):
        if not self.allowed():
            return self.reply(403, {'error': 'Accès local uniquement.'})
        if self.path == '/api/reference':
            return self.upload_reference()
        if self.path != '/api/generate':
            return self.reply(404, {'error': 'Route inconnue.'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 32768:
                return self.reply(400, {'error': 'Description trop longue ou vide.'})
            data = json.loads(self.rfile.read(size))
            text = data.get('prompt', '')
            shape = data.get('format', 'square')
            seed = data.get('seed')
            if not isinstance(text, str) or not text.strip() or len(text) > 6000 or shape not in FORMATS:
                return self.reply(400, {'error': 'Ajoute une description (6 000 caractères maximum) et un format valide.'})
            if seed is None:
                seed = secrets.randbelow(2**32)
            if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
                return self.reply(400, {'error': 'La seed doit être un entier entre 0 et 4294967295.'})
            try:
                model = model_info(data.get('model', DEFAULT_MODEL))
            except ValueError as error:
                return self.reply(400, {'error': str(error)})
            reference = data.get('reference')
            if reference:
                if not model.get('can_edit'):
                    return self.reply(400, {'error': 'Choisis Qwen pour retoucher une image.'})
                if not isinstance(reference, str) or not reference.startswith('atelier_ref_') or not reference.endswith('.png') or any(c in reference for c in '/\\:'):
                    return self.reply(400, {'error': 'Image de référence invalide.'})
                if not (ROOT / 'ComfyUI/input' / reference).is_file():
                    return self.reply(400, {'error': 'Image introuvable. Ajoute-la à nouveau.'})
            with LOCK:
                old = active_job()
                if old and job_status(old)['state'] in ('queued', 'running'):
                    return self.reply(409, {'error': 'Une image est déjà en cours de création.'})
                response = requests.post(COMFY + '/prompt', json=make_prompt(text.strip(), shape, seed, model, reference), timeout=30)
                if not response.ok:
                    return self.reply(502, {'error': 'ComfyUI a refusé le workflow : ' + response.text[:2000]})
                job = {'id': response.json()['prompt_id'], 'prompt': text.strip(), 'format': shape, 'seed': seed, 'model': model['name'], 'reference': reference, 'started': time.time()}
                temp = STATE.with_suffix('.tmp')
                temp.write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8')
                temp.replace(STATE)
            self.reply(200, job)
        except (ValueError, TypeError, AttributeError):
            self.reply(400, {'error': 'Paramètres invalides.'})
        except requests.RequestException:
            self.reply(503, {'error': 'ComfyUI ne répond pas. Vérifie son démarrage avant de réessayer.'})
        except OSError as error:
            self.reply(500, {'error': 'Impossible d’enregistrer la génération : ' + str(error)})

    def upload_reference(self):
        self.close_connection = True
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 20 * 1024**2:
                return self.reply(400, {'error': 'Choisis une image PNG, JPEG ou WebP de moins de 20 Mo.'})
            self.connection.settimeout(60)
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError('Transfert interrompu.')
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ('PNG', 'JPEG', 'WEBP') or source.width * source.height > 25_000_000:
                    raise ValueError('Format non pris en charge ou image de plus de 25 mégapixels.')
                picture = ImageOps.exif_transpose(source).convert('RGB')
                picture.thumbnail((1536, 1536))
                filename = 'atelier_ref_' + secrets.token_hex(12) + '.png'
                directory = ROOT / 'ComfyUI/input'
                directory.mkdir(parents=True, exist_ok=True)
                picture.save(directory / filename)
            self.reply(201, {'name': filename, 'width': picture.width, 'height': picture.height})
        except (ValueError, OSError, Image.DecompressionBombError) as error:
            self.reply(400, {'error': 'Image refusée : ' + str(error)})



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        server = ThreadingHTTPServer(('127.0.0.1', 8189), Handler)
    except OSError:
        try:
            existing = requests.get(URL + '/api/status', timeout=3).json()
            if existing.get('app') == 'atelier-images':
                if not args.no_browser:
                    webbrowser.open(URL)
                return
        except (requests.RequestException, ValueError):
            pass
        raise RuntimeError('Le port 8189 est déjà utilisé par une autre application.')
    threading.Thread(target=start_comfy, daemon=True).start()
    print(f'Atelier Images : {URL}', flush=True)
    if not args.no_browser:
        webbrowser.open(URL)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
