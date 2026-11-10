"""Local Qwen Image 2.1 generation, single-reference editing and character references.

fast=True applies the LightX2V Lightning v2-RL LoRA: 4 steps, CFG 1, with the exact sigma
schedule published in its inference_config.json (setting only 4 steps does not reproduce it).
"""
MODEL = 'qwen-image-2.1-UC-Q4_K_M.gguf'
ENCODER = 'qwen3vl_8b_int8_convrot.safetensors'
VAE = 'qwen_image_2.1_vae_bf16.safetensors'
LIGHTNING_LORA = 'qwen21_lightning_v2_rl_4steps_rank64.safetensors'
LIGHTNING_SIGMAS = '1.0, 0.95418, 0.89508, 0.704534, 0.0'
STEPS = 28
MAX_REFERENCES = 4


def make_qwen_prompt(text, width, height, seed, reference=None, fast=False, references=None, steps=None, sigmas=None):
    """reference: user image to edit (output keeps its proportions).
    references: character sheets that guide a new image at the chosen format."""
    references = list(references or [])[:MAX_REFERENCES]
    steps = steps or (4 if fast else STEPS)
    graph = {
        '1': {'class_type': 'UnetLoaderGGUF', 'inputs': {'unet_name': MODEL}},
        # Let ComfyUI execute the encoder on CUDA with partial RAM offloading.
        # Forcing CPU here dominated generation time on the 8 GB RTX 5060.
        '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': ENCODER, 'type': 'qwen_image', 'device': 'default'}},
        '3': {'class_type': 'TextEncodeQwenImage21', 'inputs': {'clip': ['2', 0], 'prompt': text, 'negative_prompt': '', 'resolution': 512}},
        '5': {'class_type': 'EmptyLatentImage', 'inputs': {'width': width, 'height': height, 'batch_size': 1}},
        '6': {'class_type': 'KSampler', 'inputs': {'model': ['10', 0], 'positive': ['3', 0], 'negative': ['3', 1], 'latent_image': ['5', 0], 'seed': seed, 'steps': steps, 'cfg': 1.0, 'sampler_name': 'euler', 'scheduler': 'simple', 'denoise': 1.0}},
        '7': {'class_type': 'VAELoader', 'inputs': {'vae_name': VAE}},
        '8': {'class_type': 'VAEDecode', 'inputs': {'samples': ['6', 0], 'vae': ['7', 0]}},
        '9': {'class_type': 'SaveImage', 'inputs': {'images': ['8', 0], 'filename_prefix': 'Atelier_QwenFast' if fast else 'Atelier_Qwen'}},
        '10': {'class_type': 'QwenImage21Cache', 'inputs': {'model': ['1', 0], 'device': 'cpu', 'dtype': 'default'}},
    }
    specs = {
        '1': ([30, 30], [], [('MODEL', 'MODEL')], [MODEL]),
        '2': ([30, 200], [], [('CLIP', 'CLIP')], [ENCODER, 'qwen_image', 'default']),
        '3': ([430, 210], [('clip', 'CLIP')], [('positive', 'CONDITIONING'), ('negative', 'CONDITIONING'), ('latent', 'LATENT')], [text, '', 512]),
        '5': ([440, 650], [], [('LATENT', 'LATENT')], [width, height, 1]),
        '6': ([900, 250], [('model', 'MODEL'), ('positive', 'CONDITIONING'), ('negative', 'CONDITIONING'), ('latent_image', 'LATENT')], [('LATENT', 'LATENT')], [seed, 'fixed', steps, 1.0, 'euler', 'simple', 1.0]),
        '7': ([30, 420], [], [('VAE', 'VAE')], [VAE]),
        '8': ([1320, 220], [('samples', 'LATENT'), ('vae', 'VAE')], [('IMAGE', 'IMAGE')], []),
        '9': ([1740, 220], [('images', 'IMAGE')], [], [graph['9']['inputs']['filename_prefix']]),
        '10': ([450, 30], [('model', 'MODEL')], [('MODEL', 'MODEL')], ['cpu', 'default']),
    }
    images = ([reference] if reference else []) + references
    if images:
        graph['3']['inputs']['vae'] = ['7', 0]
        specs['3'][1].append(('vae', 'VAE'))
    for index, name in enumerate(images, start=1):
        key = '11' if (reference and index == 1) else str(19 + index)
        graph[key] = {'class_type': 'AtelierLoadReference', 'inputs': {'image': name}}
        specs[key] = ([30, 650 + 160 * index], [], [('IMAGE', 'IMAGE')], [name])
        graph['3']['inputs'][f'images.image_{index}'] = [key, 0]
        specs['3'][1].append((f'images.image_{index}', 'IMAGE'))
    if reference:
        # Editing keeps the proportions of the edited image.
        graph['6']['inputs']['latent_image'] = ['3', 2]
        del graph['5'], specs['5']
    if fast:
        schedule = sigmas or LIGHTNING_SIGMAS
        graph['12'] = {'class_type': 'LoraLoaderModelOnly', 'inputs': {'model': ['1', 0], 'lora_name': LIGHTNING_LORA, 'strength_model': 1.0}}
        specs['12'] = ([30, 110], [('model', 'MODEL')], [('MODEL', 'MODEL')], [LIGHTNING_LORA, 1.0])
        graph['10']['inputs']['model'] = ['12', 0]
        graph['13'] = {'class_type': 'KSamplerSelect', 'inputs': {'sampler_name': 'euler'}}
        specs['13'] = ([450, 470], [], [('SAMPLER', 'SAMPLER')], ['euler'])
        graph['14'] = {'class_type': 'ManualSigmas', 'inputs': {'sigmas': schedule}}
        specs['14'] = ([450, 560], [], [('SIGMAS', 'SIGMAS')], [schedule])
        latent = graph['6']['inputs']['latent_image']
        graph['6'] = {'class_type': 'SamplerCustom', 'inputs': {'model': ['10', 0], 'add_noise': True, 'noise_seed': seed, 'cfg': 1.0,
                      'positive': ['3', 0], 'negative': ['3', 1], 'sampler': ['13', 0], 'sigmas': ['14', 0], 'latent_image': latent}}
        specs['6'] = ([900, 250], [('model', 'MODEL'), ('positive', 'CONDITIONING'), ('negative', 'CONDITIONING'), ('sampler', 'SAMPLER'),
                      ('sigmas', 'SIGMAS'), ('latent_image', 'LATENT')], [('output', 'LATENT'), ('denoised_output', 'LATENT')], [True, seed, 'fixed', 1.0])
    nodes, links = [], []
    for key, node in graph.items():
        pos, inputs, outputs, widgets = specs[key]
        nodes.append({'id': int(key), 'type': node['class_type'], 'pos': pos, 'size': [360, 300] if key in ('3', '6', '9', '11') else [360, 140],
                      'flags': {}, 'order': len(nodes), 'mode': 0, 'properties': {'Node name for S&R': node['class_type']},
                      'inputs': [{'name': name, 'type': kind, 'link': None} for name, kind in inputs],
                      'outputs': [{'name': name, 'type': kind, 'links': [], 'slot_index': i} for i, (name, kind) in enumerate(outputs)], 'widgets_values': widgets})
    by_id = {node['id']: node for node in nodes}
    for node in nodes:
        for slot, socket in enumerate(node['inputs']):
            source, source_slot = graph[str(node['id'])]['inputs'][socket['name']]
            link_id = len(links) + 1
            links.append([link_id, int(source), source_slot, node['id'], slot, socket['type']])
            socket['link'] = link_id
            by_id[int(source)]['outputs'][source_slot]['links'].append(link_id)
    workflow = {'last_node_id': max(by_id), 'last_link_id': len(links), 'nodes': nodes, 'links': links, 'groups': [], 'config': {}, 'extra': {}, 'version': 0.4}
    return {'prompt': graph, 'extra_data': {'extra_pnginfo': {'workflow': workflow}}}
