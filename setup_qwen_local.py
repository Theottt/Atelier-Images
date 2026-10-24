import runpy
from pathlib import Path
setup = runpy.run_path(str(Path(__file__).resolve().with_name('setup_flux_schnell.py')))
repo = 'abenzerps/Qwen-Image-2.1-Uncensored-GGUF'
for target, source in [
 ('unet/qwen-image-2.1-UC-Q4_K_M.gguf', 'qwen-image-2.1-UC-Q4_K_M.gguf'),
 ('text_encoders/qwen3vl_8b_int8_convrot.safetensors', 'text_encoders/qwen3vl_8b_int8_convrot.safetensors'),
 ('vae/qwen_image_2.1_vae_bf16.safetensors', 'vae/qwen_image_2.1_vae_bf16.safetensors')]:
    setup['download'](target, repo, source)
