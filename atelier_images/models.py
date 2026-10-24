"""List configured local image models without loading weights onto the GPU."""
from functools import lru_cache
from pathlib import Path

import gguf
from qwen_workflow import MODEL as QWEN_MODEL, ENCODER as QWEN_ENCODER, VAE as QWEN_VAE

MODEL_DIR = Path(__file__).resolve().parent.parent / 'ComfyUI/models/unet'
DEFAULT_MODEL = 'flux1-schnell-Q4_K_S.gguf'


def model_path(name):
    if not isinstance(name, str) or not name or len(name) > 180 or any(c in name for c in '/\\:<>"|?*') or any(ord(c) < 32 for c in name):
        raise ValueError('Nom de fichier invalide.')
    if not name.lower().endswith('.gguf') or name.rstrip(' .') != name:
        raise ValueError('Choisis le fichier .gguf du modèle FLUX.1, pas une archive, un LoRA ou un fichier .safetensors.')
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))}:
        raise ValueError('Nom de fichier réservé par Windows.')
    path = MODEL_DIR / name
    if path.resolve().parent != MODEL_DIR.resolve():
        raise ValueError('Le fichier doit rester dans le dossier des modèles.')
    return path


def inspect_model(path):
    reader = None
    try:
        reader = gguf.GGUFReader(str(path))
        field = reader.get_field('general.architecture')
        arch = field.contents() if field else None
        tensors = {t.name.removeprefix('model.diffusion_model.'): t for t in reader.tensors}
        def shape(name):
            original = reader.get_field('comfy.gguf.orig_shape.' + tensors[name].name)
            return tuple(original.contents()) if original else tuple(int(n) for n in reversed(tensors[name].shape))
        if arch not in (None, 'flux') or not {'img_in.weight', 'txt_in.weight', 'final_layer.linear.weight'}.issubset(tensors):
            raise ValueError('Ce fichier n’est pas un modèle de génération FLUX.1 compatible. SDXL, FLUX.2, modèles de langage et encodeurs demandent un autre workflow.')
        if shape('img_in.weight') != (3072, 64) or shape('txt_in.weight') != (3072, 4096) or shape('final_layer.linear.weight') != (64, 3072):
            raise ValueError('Cette variante FLUX nécessite un autre workflow (par exemple Fill ou un modèle de contrôle).')
        if not any(n.startswith('double_blocks.') for n in tensors) or not any(n.startswith('single_blocks.') for n in tensors):
            raise ValueError('Ce fichier ne contient pas les blocs du modèle FLUX.1 complet.')
        variant = 'dev' if any(n.startswith('guidance_in.') for n in tensors) else 'schnell'
        return {'variant': variant, 'steps': 20 if variant == 'dev' else 4}
    except ValueError:
        raise
    except Exception as error:
        raise ValueError('Fichier GGUF illisible ou incomplet. Vérifie que le téléchargement est terminé.') from error
    finally:
        if reader is not None:
            reader.data._mmap.close()


@lru_cache(maxsize=64)
def cached_inspection(path, size, mtime):
    return inspect_model(Path(path))


def model_info(name):
    path = model_path(name)
    if not path.is_file():
        raise ValueError('Ce modèle est introuvable. Actualise la liste des modèles installés.')
    stat = path.stat()
    if name == QWEN_MODEL:
        for component in [MODEL_DIR.parent / 'text_encoders' / QWEN_ENCODER, MODEL_DIR.parent / 'vae' / QWEN_VAE]:
            if not component.is_file():
                raise ValueError('Installation Qwen en cours : composant manquant ' + component.name)
        return {'name': name, 'label': 'Qwen Image 2.1 Uncensored · génération et retouche', 'size': stat.st_size,
                'family': 'qwen21', 'variant': 'qwen21', 'steps': 28, 'can_edit': True}
    return {'name': path.name, 'size': stat.st_size, 'family': 'flux', 'can_edit': False, **cached_inspection(str(path), stat.st_size, stat.st_mtime_ns)}


def list_models():
    found, excluded = [], []
    for path in sorted(MODEL_DIR.glob('*.gguf')):
        try:
            found.append(model_info(path.name))
        except (ValueError, OSError) as error:
            excluded.append({'name': path.name, 'reason': str(error)})
    return {'models': found, 'excluded': excluded, 'default': DEFAULT_MODEL}
