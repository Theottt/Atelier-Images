"""Download the SD 1.5 EMA-only checkpoint, with resume and SHA-256 verification."""
import runpy
from pathlib import Path

setup = runpy.run_path(str(Path(__file__).resolve().with_name('setup_flux_schnell.py')))
setup['download']('checkpoints/v1-5-pruned-emaonly.safetensors',
                  'stable-diffusion-v1-5/stable-diffusion-v1-5',
                  'v1-5-pruned-emaonly.safetensors')
