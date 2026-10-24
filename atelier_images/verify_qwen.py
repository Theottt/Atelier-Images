"""Run a real generation and edit through Atelier Images after setup completes."""
import json
import argparse
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qwen_workflow import MODEL

ROOT = Path(__file__).resolve().parent.parent
API = 'http://127.0.0.1:8189'


def generate(prompt, reference=None):
    response = requests.post(API + '/api/generate', json={'model': MODEL, 'prompt': prompt, 'format': 'square', 'seed': 8765, 'reference': reference}, timeout=60)
    response.raise_for_status()
    job_id = response.json()['id']
    print('Queued ' + job_id, flush=True)
    started = time.monotonic()
    last_report = 0
    while time.monotonic() - started < 1800:
        response = requests.get(API + '/api/job', timeout=30)
        response.raise_for_status()
        result = response.json()
        if result['id'] != job_id:
            raise RuntimeError('Another job replaced the test; not submitting further work.')
        if result['state'] == 'error':
            raise RuntimeError(result['error'])
        if result['state'] == 'done':
            print('SUCCESS ' + json.dumps(result), flush=True)
            return result
        elapsed = int(time.monotonic() - started)
        if elapsed - last_report >= 20:
            print(f'{result["state"]}: {elapsed}s', flush=True)
            last_report = elapsed
        time.sleep(3)
    raise TimeoutError('Generation still running after 30 minutes; inspect ComfyUI.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--edit-image')
    args = parser.parse_args()
    for _ in range(600):
        result = requests.get(API + '/api/models', timeout=30).json()
        if any(model['name'] == MODEL for model in result['models']) and requests.get(API + '/api/status', timeout=30).json()['ready']:
            break
        time.sleep(3)
    else:
        raise TimeoutError('Qwen installation is not complete.')
    generated = {'state': 'done', 'images': [args.edit_image]} if args.edit_image else generate('A watercolor illustration of a bright red ceramic teapot on a wooden table, a sunlit garden in the background, soft natural light, clean composition.')
    source = ROOT / 'ComfyUI/output' / generated['images'][0]
    with source.open('rb') as stream:
        response = requests.post(API + '/api/reference', data=stream, headers={'Content-Type': 'application/octet-stream'}, timeout=60)
    response.raise_for_status()
    edited = generate('Change the red teapot to blue. Keep the same teapot shape, wooden table, garden background and watercolor style.', response.json()['name'])
    (ROOT / 'atelier_images/qwen_verified.json').write_text(json.dumps({'generated': generated, 'edited': edited}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
