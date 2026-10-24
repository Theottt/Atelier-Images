r"""Run with .\python_embeded\python.exe -s setup_flux_schnell.py."""
import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
import requests
from huggingface_hub import get_hf_file_metadata

ROOT = Path(__file__).resolve().parent
EXT = ROOT / 'ComfyUI/custom_nodes/ComfyUI-GGUF'
MODELS = [
    ('unet/flux1-schnell-Q4_K_S.gguf', 'city96/FLUX.1-schnell-gguf', 'flux1-schnell-Q4_K_S.gguf'),
    ('clip/clip_l.safetensors', 'comfyanonymous/flux_text_encoders', 'clip_l.safetensors'),
    ('clip/t5xxl_fp16.safetensors', 'comfyanonymous/flux_text_encoders', 't5xxl_fp16.safetensors'),
    ('vae/ae.safetensors', 'Comfy-Org/Lumina_Image_2.0_Repackaged', 'split_files/vae/ae.safetensors'),
]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(relative, repo, filename):
    target = ROOT / 'ComfyUI/models' / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    url = f'https://huggingface.co/{repo}/resolve/main/{filename}'
    meta = get_hf_file_metadata(url, timeout=60)
    size, sha = meta.size, meta.etag
    if not size or not sha or len(sha) != 64:
        raise RuntimeError(f'Missing size/SHA256 metadata for {filename}')
    if target.exists():
        if target.stat().st_size == size and digest(target) == sha:
            print(f'Verified existing {relative}', flush=True)
            return
        raise RuntimeError(f'Existing file failed validation; move it aside before retrying: {target}')
    partial = target.with_suffix(target.suffix + '.part')
    offset = partial.stat().st_size if partial.exists() else 0
    if shutil.disk_usage(ROOT).free < max(0, size - offset) + 1024**3:
        raise RuntimeError('Insufficient free disk space')
    for attempt in range(8):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset == size:
            break
        if offset > size:
            raise RuntimeError(f'Partial file larger than expected: {partial}')
        try:
            headers = {'Range': f'bytes={offset}-'} if offset else {}
            with requests.get(url, headers=headers, stream=True, timeout=(30, 120)) as response:
                response.raise_for_status()
                if offset and response.status_code == 206:
                    if not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'):
                        raise RuntimeError('Server returned unexpected download range')
                    mode = 'ab'
                else:
                    offset, mode = 0, 'wb'
                print(f'Downloading {relative}: {offset / 1024**3:.2f}/{size / 1024**3:.2f} GiB', flush=True)
                last = time.monotonic()
                with partial.open(mode) as stream:
                    for chunk in response.iter_content(8 * 1024**2):
                        stream.write(chunk)
                        offset += len(chunk)
                        if time.monotonic() - last > 20:
                            print(f'  {filename}: {offset / size:.1%}', flush=True)
                            last = time.monotonic()
            if offset != size:
                raise requests.ConnectionError(f'Incomplete download: {offset}/{size}')
            break
        except requests.RequestException as error:
            print(f'Download attempt {attempt + 1} failed: {type(error).__name__}', flush=True)
            if attempt == 7:
                raise
            time.sleep(5)
    print(f'Checking SHA256: {filename}', flush=True)
    if partial.stat().st_size != size or digest(partial) != sha:
        raise RuntimeError(f'Checksum mismatch: {partial}; move it aside before retrying')
    partial.replace(target)
    print(f'VERIFIED {relative} ({size:,} bytes)', flush=True)


def main():
    if not EXT.exists():
        EXT.parent.mkdir(parents=True, exist_ok=True)
        git = shutil.which('git')
        if git:
            subprocess.run([git, 'clone', 'https://github.com/city96/ComfyUI-GGUF.git', str(EXT)], check=True)
        else:
            print('Git unavailable; installing official GitHub source ZIP (no Git history).', flush=True)
            response = requests.get('https://codeload.github.com/city96/ComfyUI-GGUF/zip/refs/heads/main', timeout=120)
            response.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                for member in archive.infolist():
                    relative = Path(*Path(member.filename).parts[1:])
                    destination = EXT / relative
                    if not destination.resolve().is_relative_to(EXT.resolve()):
                        raise RuntimeError('Unsafe ZIP path')
                    if member.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as source, destination.open('wb') as output:
                            shutil.copyfileobj(source, output)
    requirements = EXT / 'requirements.txt'
    # Install only this extension's dependencies; do not install ComfyUI's video dependencies.
    subprocess.run([sys.executable, '-s', '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(requirements)], check=True)
    failures = []
    for model in MODELS:
        try:
            download(*model)
        except Exception as error:
            print(f'FAILED {model[0]}: {error}', flush=True)
            failures.append(model[0])
    if failures:
        raise RuntimeError('Setup incomplete: ' + ', '.join(failures))
    print('SUCCESS: extension installed and all four model files verified.', flush=True)
    print(r'Launch: .\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build', flush=True)


if __name__ == '__main__':
    main()
