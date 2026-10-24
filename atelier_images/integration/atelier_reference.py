"""Load Atelier's normalized still images without the optional PyAV video reader."""
from pathlib import Path

import numpy as np
from PIL import Image
import torch

import folder_paths
import comfy.model_management


def reference_path(name):
    root = Path(folder_paths.get_input_directory()).resolve()
    if not isinstance(name, str) or not name.startswith('atelier_ref_') or any(c in name for c in '/\\:'):
        raise ValueError('Invalid Atelier reference name')
    path = (root / name).resolve()
    if path.parent != root or path.suffix != '.png' or not path.is_file():
        raise ValueError('Atelier reference is missing or outside the input folder')
    return path


class AtelierLoadReference:
    @classmethod
    def INPUT_TYPES(cls):
        files = sorted(p.name for p in Path(folder_paths.get_input_directory()).glob('atelier_ref_*.png') if p.is_file())
        return {'required': {'image': (files,)}}

    RETURN_TYPES = ('IMAGE',)
    FUNCTION = 'load_image'
    CATEGORY = 'image/Atelier'

    def load_image(self, image):
        with Image.open(reference_path(image)) as source:
            pixels = np.array(source.convert('RGB'), dtype=np.float32) / 255.0
        tensor = torch.from_numpy(pixels).unsqueeze(0)
        return (tensor.to(device=comfy.model_management.intermediate_device(), dtype=comfy.model_management.intermediate_dtype()),)

    @classmethod
    def IS_CHANGED(cls, image):
        stat = reference_path(image).stat()
        return (stat.st_size, stat.st_mtime_ns)

    @classmethod
    def VALIDATE_INPUTS(cls, image):
        try:
            reference_path(image)
        except ValueError as error:
            return str(error)
        return True


NODE_CLASS_MAPPINGS = {'AtelierLoadReference': AtelierLoadReference}
NODE_DISPLAY_NAME_MAPPINGS = {'AtelierLoadReference': 'Atelier : charger une image fixe'}
