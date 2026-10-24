# Atelier Images (One-Click Local AI Image Generator & Editor)

![Local-First](https://img.shields.io/badge/Local--First-on_your_PC-26734d)
![Privacy-Focused](https://img.shields.io/badge/Privacy--Focused-local_inference-26734d)
![RTX Optimized](https://img.shields.io/badge/RTX-Optimized-76b900)
![ComfyUI Backend](https://img.shields.io/badge/Backend-ComfyUI-333333)

A clean, chat-inspired web interface for creating and editing images on your Windows PC.
Atelier Images hides ComfyUI's node graphs behind a prompt box, a model selector and a gallery.
After setup, one double-click starts the local services and opens your browser.

The interface currently uses French labels. This repository contains Atelier's source code;
ComfyUI, Python, model weights and generated images are installed separately.

## Features

- Text-to-image with FLUX.1 [schnell] GGUF Q4_K_S.
- Text-to-image and single-reference image editing with Qwen Image 2.1 Uncensored.
- Square, portrait and landscape generation; editing follows the reference aspect ratio.
- Seeds, image downloads and a gallery with prompt reuse.
- A Windows GUI launcher that starts the servers without console windows, waits for readiness
  and reuses running services.
- Local GPU inference, with CPU text-encoder offloading for limited VRAM.

## Requirements

- Windows with a working NVIDIA ComfyUI portable installation and compatible GPU drivers/PyTorch.
- A ComfyUI build supporting Qwen Image 2.1 nodes when using Qwen, plus
  [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF).
- Tested development hardware: NVIDIA RTX 5060 Laptop GPU (8 GB VRAM), 32 GB system RAM.
  Performance on other configurations varies; Qwen is substantially slower than FLUX.
- Roughly 21 GiB for the listed weights, plus space for ComfyUI, Python, downloads and outputs.
- Windows PowerShell and the .NET Framework C# compiler for building the launcher.

## Quick start

### 1. Place the source in your portable installation

Start with a working [ComfyUI Windows portable installation](https://github.com/Comfy-Org/ComfyUI).
Download this repository's source and copy its contents into the portable root, alongside
`ComfyUI/` and `python_embeded/`. Merge the source folders; do not replace your runtime folders.

```text
ComfyUI_windows_portable/
  ComfyUI/                  # installed separately
  python_embeded/           # supplied by ComfyUI portable
  atelier_images/           # this repository
  start.ps1
  build_launcher.ps1
  prepare_atelier.py
  setup_flux_schnell.py
  setup_qwen_local.py
```

### 2. Install the extension and models

Open PowerShell in that root. These commands download dependencies and weights from the internet:

```powershell
.\python_embeded\python.exe -s -m pip install requests huggingface_hub
.\python_embeded\python.exe -s setup_flux_schnell.py
# Optional: download Qwen generation/editing weights as well.
.\python_embeded\python.exe -s setup_qwen_local.py
.\python_embeded\python.exe -s prepare_atelier.py
```

The FLUX setup installs ComfyUI-GGUF and its dependencies. Model downloads resume through `.part`
files and are checked against SHA-256 metadata. The preparation script installs Atelier's Pillow
reference-image node and, if needed, adds `qwen_image21` to the GGUF loader architecture list.
It saves a backup before that change. The ComfyUI core must already support this architecture.
Restart ComfyUI after preparing the integration. These scripts do not install PyAV or video dependencies.

For manual downloads, place the exact filenames below in these folders:

| Model / component | Path relative to the portable root | Download source |
| --- | --- | --- |
| FLUX Schnell Q4_K_S | `ComfyUI/models/unet/flux1-schnell-Q4_K_S.gguf` | [city96](https://huggingface.co/city96/FLUX.1-schnell-gguf) |
| CLIP-L | `ComfyUI/models/clip/clip_l.safetensors` | [FLUX encoders](https://huggingface.co/comfyanonymous/flux_text_encoders) |
| T5 XXL FP16 | `ComfyUI/models/clip/t5xxl_fp16.safetensors` | [FLUX encoders](https://huggingface.co/comfyanonymous/flux_text_encoders) |
| FLUX VAE | `ComfyUI/models/vae/ae.safetensors` | [Comfy-Org, split_files/vae](https://huggingface.co/Comfy-Org/Lumina_Image_2.0_Repackaged) |
| Qwen 2.1 Uncensored Q4_K_M | `ComfyUI/models/unet/qwen-image-2.1-UC-Q4_K_M.gguf` | [Qwen quantized repository](https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF) |
| Qwen text encoder | `ComfyUI/models/text_encoders/qwen3vl_8b_int8_convrot.safetensors` | Same repository, `text_encoders/` |
| Qwen VAE | `ComfyUI/models/vae/qwen_image_2.1_vae_bf16.safetensors` | Same repository, `vae/` |

Arbitrary GGUF files are not interchangeable: each architecture needs compatible loaders,
text encoders, a VAE and a workflow. The supported Qwen configuration uses local quantized weights;
it does not call the Hugging Face Space or reproduce its hosted BF16 setup exactly.

### 3. Build and launch

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build_launcher.ps1
```

Double-click **Atelier Images.exe** in the portable root. It opens
**http://127.0.0.1:8189** once both servers are ready. Initial startup can take several minutes.
The executable is a small launcher, not a bundle containing Python or models; keep it beside
`start.ps1` and the runtime folders. It is built locally and excluded from source control.
The execution-policy option applies only to the invoked PowerShell process.

The executable is unsigned. Some Windows application-control policies may require approval or
a trusted signature. It has been confirmed working by the project owner through Explorer.
For diagnosis, run `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start.ps1` in a terminal.

### 4. Create or edit

Choose a model under **Mon modèle**, enter a description, select a format and click **Créer mon image**.
With Qwen, add a PNG, JPEG or WebP reference to edit an existing image. Remove the reference to return
to text-to-image. Reference uploads are limited to 20 MB / 25 megapixels and normalized locally.
Closing the browser leaves the local servers running for the next session.

## Privacy and local storage

Atelier's generation/editing requests go to the local ComfyUI server. Its frontend has no analytics,
remote fonts or CDN dependencies. Servers bind to loopback: Atelier on `127.0.0.1:8189`,
ComfyUI on `127.0.0.1:8188`. Setup downloads and optional upstream ComfyUI services are separate
from this local generation path; this project does not enforce a machine-wide network block.
The badges in this README are externally hosted documentation images, not application resources.

| Location | Contents |
| --- | --- |
| `ComfyUI/output/` | Generated PNGs, **including prompt and workflow metadata** |
| `ComfyUI/input/atelier_ref_*.png` | Normalized copies of uploaded reference images |
| `atelier_images/active_job.json` | Latest job, prompt and parameters |
| `atelier_images/*.log` | Startup and diagnostic logs |
| `ComfyUI/user/` | ComfyUI settings, saved workflows and asset database |
| Browser local storage | Last selected model (`atelier-model`) |

Sharing an original PNG can also share its prompt/workflow. Files are not encrypted by Atelier.
Removing a reference from the form does not delete its saved copy. The gallery displays the latest
150 matching outputs without deleting older files. Private runtime files are excluded by `.gitignore`.

## Development

The frontend is maintained directly in `atelier_images/dist/` (HTML, CSS and JavaScript), with no
Node build step. `atelier_images/server.py` serves the frontend and constructs local ComfyUI requests.
The FLUX template lives in `atelier_images/workflows/`; the custom reference node source lives in
`atelier_images/integration/`. `prepare_atelier.py` installs that node into the separate runtime.

Run the workflow tests from the portable root:

```powershell
.\python_embeded\python.exe -s atelier_images\test_workflows.py
.\python_embeded\python.exe -s tests\test_prepare.py
```

For launch failures, inspect `atelier_images/launcher.log`, `launcher-server.stderr.log` and
`comfyui.log`. Avoid attaching private prompts, output PNGs or logs to public issues without reviewing them.

## License

Atelier's original source is released under the [MIT License](LICENSE). ComfyUI, ComfyUI-GGUF,
Python, dependencies and model weights retain their own licenses and are not redistributed here.
Check the relevant model repository terms before use or redistribution.

## Credits / Acknowledgments

Thanks to the ComfyUI community, city96 and the creators and maintainers of FLUX, Qwen and their
quantized model releases. Built with the assistance of AI coding tools.
