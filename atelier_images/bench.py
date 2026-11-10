"""Speed benchmark of the local pipelines, straight against ComfyUI (the Atelier queue is not used).

Usage (portable Python, ComfyUI running on 8188):
    python_embeded\\python.exe -s atelier_images\\bench.py flux qwen qwen_fast --seeds 11 22
Each configuration starts with one warm-up image (model loading) that is reported separately.
Results go to atelier_images/bench_results/<time>.json; images keep their usual Atelier prefix.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qwen_workflow import make_qwen_prompt  # noqa: E402

COMFY = 'http://127.0.0.1:8188'
HERE = Path(__file__).resolve().parent

# Generic test set: every prompt lists details that can be checked one by one on the image.
PROMPTS = [
    ('blob', 'a cute round pink blob monster with exactly two big eyes, a single green leaf sprout on top of its head, short stubby legs, '
             'holding a tiny blue umbrella, stylized 3D cartoon render, plain white background'),
    ('coins', 'three gold coins stacked next to a red sword lying on a wooden table, stylized 3D cartoon render'),
    ('duo', 'a blue ice puppy monster with an icicle tail sitting on the left, a green cactus monster with a pink flower on its head standing on the right, '
            'sandy desert background, stylized 3D cartoon render'),
    ('chase', 'a giant purple guardian monster with glowing red eyes chasing a small blocky toy character who carries a pink baby monster, '
              'green meadow, stylized 3D cartoon render'),
    ('egg', 'a black volcanic monster egg with glowing orange lava cracks, sitting on a grey stone pedestal, inside a dark cave with two torches on the wall, '
            'stylized 3D cartoon render'),
]


def flux_payload(text, seed, width, height):
    import server
    return server.make_prompt(text, 'square' if width == height else ('landscape' if width > height else 'portrait'), seed)


def payload_for(config, text, seed, size, references=None):
    width, height = size
    if config == 'flux':
        return flux_payload(text, seed, width, height)
    return make_qwen_prompt(text, width, height, seed, fast=config == 'qwen_fast', references=references)


def run(payload):
    started = time.perf_counter()
    response = requests.post(COMFY + '/prompt', json=payload, timeout=30)
    response.raise_for_status()
    prompt_id = response.json()['prompt_id']
    while True:
        time.sleep(0.5)
        entry = requests.get(COMFY + '/history/' + prompt_id, timeout=10).json().get(prompt_id)
        if not entry:
            continue
        status = entry.get('status', {})
        if status.get('status_str') == 'error':
            messages = [m[1].get('exception_message', '') for m in status.get('messages', []) if m[0] == 'execution_error']
            raise RuntimeError(messages[-1] if messages else 'ComfyUI error')
        if status.get('completed'):
            images = [i['filename'] for out in entry.get('outputs', {}).values() for i in out.get('images', [])]
            return time.perf_counter() - started, images


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('configs', nargs='+', choices=['flux', 'qwen', 'qwen_fast'])
    parser.add_argument('--seeds', nargs='+', type=int, default=[11, 22])
    parser.add_argument('--size', nargs=2, type=int, default=[512, 512])
    args = parser.parse_args()
    report = {'size': args.size, 'seeds': args.seeds, 'results': []}
    for config in args.configs:
        warm, images = run(payload_for(config, 'a red apple on a table', 1, args.size))
        report['results'].append({'config': config, 'prompt': 'warmup', 'seed': 1, 'seconds': round(warm, 1), 'images': images})
        print(f'{config} warm-up {warm:.1f}s', flush=True)
        for name, text in PROMPTS:
            for seed in args.seeds:
                seconds, images = run(payload_for(config, text, seed, args.size))
                report['results'].append({'config': config, 'prompt': name, 'seed': seed, 'seconds': round(seconds, 1), 'images': images})
                print(f'{config} {name} seed={seed} {seconds:.1f}s {images}', flush=True)
    for config in args.configs:
        times = [r['seconds'] for r in report['results'] if r['config'] == config and r['prompt'] != 'warmup']
        print(f'== {config}: mean {sum(times) / len(times):.1f}s over {len(times)} images', flush=True)
    out = HERE / 'bench_results'
    out.mkdir(exist_ok=True)
    (out / time.strftime('%Y%m%d-%H%M%S.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
