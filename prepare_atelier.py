"""Install Atelier's reference node and enable Qwen 2.1 in the GGUF loader."""
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parent


def main():
    comfy = ROOT / 'ComfyUI'
    if not (comfy / 'main.py').is_file():
        raise RuntimeError('Place this repository in a working ComfyUI portable root first.')
    loader = comfy / 'custom_nodes/ComfyUI-GGUF/loader.py'
    if not loader.is_file():
        raise RuntimeError('Install ComfyUI-GGUF first (see README.md).')
    text = loader.read_text(encoding='utf-8')
    match = re.search(r'^IMG_ARCH_LIST\s*=\s*\{([^}]*)\}', text, re.MULTILINE)
    if not match:
        raise RuntimeError('GGUF loader layout changed. Check Qwen 2.1 support before continuing.')
    if '"qwen_image21"' not in match.group(1) and "'qwen_image21'" not in match.group(1):
        backup = loader.with_suffix('.py.atelier.bak')
        if not backup.exists():
            shutil.copy2(loader, backup)
        offset = match.end() - 1
        updated = text[:offset].rstrip().rstrip(',') + ', "qwen_image21"' + text[offset:]
        loader.write_text(updated, encoding='utf-8')
    shutil.copy2(ROOT / 'atelier_images/integration/atelier_reference.py',
                 comfy / 'custom_nodes/atelier_reference.py')
    print('Atelier reference node and GGUF Qwen 2.1 architecture ready. Restart ComfyUI if running.')


if __name__ == '__main__':
    main()
