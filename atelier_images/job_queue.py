"""Persistent sequential work. Never resubmit an uncertain GPU request automatically."""
import copy
import json
import logging
import threading
import time
import uuid

import requests

TERMINAL = {'done', 'error', 'cancelled'}


class JobQueue:
    def __init__(self, path, make_payload, comfy):
        self.path, self.make_payload, self.comfy = path, make_payload, comfy
        self.lock = threading.RLock()
        self.work_lock = threading.RLock()
        self.data = {'paused': False, 'jobs': [], 'error': ''}
        if path.exists():
            self.data = json.loads(path.read_text(encoding='utf-8'))

    def save(self):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf-8')
        temporary.replace(self.path)

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def enqueue(self, specs):
        with self.lock:
            pending = sum(j['count'] - j['completed'] for j in self.data['jobs'] if j['state'] not in TERMINAL)
            if pending + sum(s['count'] for s in specs) > 200:
                raise ValueError('La file accepte au maximum 200 images restantes.')
            jobs = [{**spec, 'id': str(uuid.uuid4()), 'state': 'queued', 'completed': 0, 'images': [],
                     'started': time.time(), 'attempt': None, 'cancel_requested': False} for spec in specs]
            # Keep at most 100 finished groups; output files remain on disk.
            old = [j for j in self.data['jobs'] if j['state'] in TERMINAL][-100:]
            active = [j for j in self.data['jobs'] if j['state'] not in TERMINAL]
            previous = self.data['jobs']
            self.data['jobs'] = old + active + jobs
            try:
                self.save()
            except OSError:
                self.data['jobs'] = previous
                raise
            return copy.deepcopy(jobs)

    def control(self, action, job_id=None):
        with self.lock:
            if action in ('pause', 'resume'):
                self.data['paused'] = action == 'pause'
                self.data['error'] = ''
            elif action == 'clear_finished':
                self.data['jobs'] = [j for j in self.data['jobs'] if j['state'] not in TERMINAL]
            elif action == 'cancel':
                job = next((j for j in self.data['jobs'] if j['id'] == job_id), None)
                if not job:
                    raise ValueError('Ce prompt ne figure plus dans la file.')
                if job['state'] not in TERMINAL:
                    job['cancel_requested'] = True
                    if not job['attempt']:
                        job['state'] = 'cancelled'
            elif action == 'dismiss':
                self.data['jobs'] = [j for j in self.data['jobs'] if not (j['id'] == job_id and j['state'] in TERMINAL)]
            else:
                raise ValueError('Commande de file inconnue.')
            self.save()
        return self.snapshot()

    def get(self, route):
        response = requests.get(self.comfy + route, timeout=5)
        response.raise_for_status()
        return response.json()

    def fail(self, job, message):
        with self.lock:
            job.update(state='error', error=message, attempt=None)
            if any(word in message.lower() for word in ('out of memory', 'allocation', 'cuda error')):
                self.data.update(paused=True, error='Mémoire insuffisante : file en pause. Ferme les autres applications avant de reprendre.')
            self.save()

    def tick(self):
        with self.work_lock:
            self._tick()

    def _tick(self):
        with self.lock:
            job = next((j for j in self.data['jobs'] if j['attempt'] and j['state'] not in TERMINAL), None)
            if job is None:
                if self.data['paused']:
                    return
                job = next((j for j in self.data['jobs'] if j['state'] == 'queued'), None)
            if job is None:
                return
            attempt = job['attempt']
        if attempt:
            history = self.get('/history/' + attempt['id']).get(attempt['id'])
            if history:
                status = history.get('status', {})
                if status.get('status_str') == 'error':
                    messages = [d.get('exception_message', 'Erreur ComfyUI') for kind, d in status.get('messages', []) if kind == 'execution_error']
                    self.fail(job, messages[-1] if messages else 'La génération a échoué.')
                elif status.get('completed'):
                    images = [i['filename'] for out in history.get('outputs', {}).values() for i in out.get('images', []) if i.get('type') == 'output']
                    if len(images) != 1:
                        self.fail(job, 'Le moteur n’a pas renvoyé exactement une image. File du prompt arrêtée.')
                        return
                    with self.lock:
                        job['images'].extend(images)
                        job['completed'] += 1
                        job['attempt'] = None
                        job['state'] = 'done' if job['completed'] == job['count'] else 'cancelled' if job['cancel_requested'] else 'queued'
                        self.save()
                return
            backend = self.get('/queue')
            present = any(item[1] == attempt['id'] for key in ('queue_running', 'queue_pending') for item in backend.get(key, []))
            if present:
                with self.lock:
                    if job['state'] != 'running':
                        job['state'] = 'running'
                        self.save()
            elif time.time() - attempt['sent_at'] > 60:
                self.fail(job, 'Exécution introuvable après une interruption. Aucun renvoi automatique pour éviter les doublons ; vérifie la galerie.')
            return

        # Do not compete with work submitted directly through ComfyUI.
        backend = self.get('/queue')
        if backend.get('queue_running') or backend.get('queue_pending'):
            return
        try:
            payload = self.make_payload(job, (job['seed'] + job['completed']) % 2**32)
        except (ValueError, OSError) as error:
            self.fail(job, str(error))
            return
        with self.lock:
            if self.data['paused'] or job['state'] != 'queued':
                return
            attempt = {'id': str(uuid.uuid4()), 'sent_at': time.time()}
            job.update(attempt=attempt, state='submitting')
            self.save()  # Persist the correlation ID before any network side effect.
        payload['prompt_id'] = attempt['id']
        # A fresh output even when the same seed/prompt is deliberately submitted twice.
        prefix = payload['prompt']['9']['inputs']['filename_prefix'] + '_' + attempt['id'][:8]
        payload['prompt']['9']['inputs']['filename_prefix'] = prefix
        for node in payload.get('extra_data', {}).get('extra_pnginfo', {}).get('workflow', {}).get('nodes', []):
            if node['id'] == 9:
                node['widgets_values'] = [prefix]
        try:
            response = requests.post(self.comfy + '/prompt', json=payload, timeout=30)
        except requests.RequestException:
            return  # Next tick reconciles history/queue; never blindly retries POST.
        if not response.ok:
            if response.status_code < 500:
                self.fail(job, 'ComfyUI a refusé le workflow : ' + response.text[:1500])
            return
        with self.lock:
            job['state'] = 'running'
            self.save()

    def run(self, stop):
        while not stop.is_set():
            try:
                self.tick()
            except requests.RequestException:
                pass  # Backend offline: preserve pending and in-flight work.
            except Exception:
                logging.exception('Queue worker stopped advancing; pending jobs preserved')
                with self.lock:
                    self.data.update(paused=True, error='Erreur de file : consulte le journal avant de reprendre.')
            stop.wait(1)
