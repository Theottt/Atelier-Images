"""Local Qwen Image 2.1 generation and single-reference editing."""
MODEL = 'qwen-image-2.1-UC-Q4_K_M.gguf'
ENCODER = 'qwen3vl_8b_int8_convrot.safetensors'
VAE = 'qwen_image_2.1_vae_bf16.safetensors'


def make_qwen_prompt(text, width, height, seed, reference=None):
    graph = {
        '1': {'class_type': 'UnetLoaderGGUF', 'inputs': {'unet_name': MODEL}},
        '2': {'class_type': 'CLIPLoader', 'inputs': {'clip_name': ENCODER, 'type': 'qwen_image', 'device': 'cpu'}},
        '3': {'class_type': 'TextEncodeQwenImage21', 'inputs': {'clip': ['2', 0], 'prompt': text, 'negative_prompt': '', 'resolution': 512}},
        '5': {'class_type': 'EmptyLatentImage', 'inputs': {'width': width, 'height': height, 'batch_size': 1}},
        '6': {'class_type': 'KSampler', 'inputs': {'model': ['10', 0], 'positive': ['3', 0], 'negative': ['3', 1], 'latent_image': ['5', 0], 'seed': seed, 'steps': 28, 'cfg': 1.0, 'sampler_name': 'euler', 'scheduler': 'simple', 'denoise': 1.0}},
        '7': {'class_type': 'VAELoader', 'inputs': {'vae_name': VAE}},
        '8': {'class_type': 'VAEDecode', 'inputs': {'samples': ['6', 0], 'vae': ['7', 0]}},
        '9': {'class_type': 'SaveImage', 'inputs': {'images': ['8', 0], 'filename_prefix': 'Atelier_Qwen'}},
        '10': {'class_type': 'QwenImage21Cache', 'inputs': {'model': ['1', 0], 'device': 'cpu', 'dtype': 'default'}},
    }
    if reference:
        graph['11'] = {'class_type': 'AtelierLoadReference', 'inputs': {'image': reference}}
        graph['3']['inputs'].update({'vae': ['7', 0], 'images.image_1': ['11', 0]})
        graph['6']['inputs']['latent_image'] = ['3', 2]
        del graph['5']
    specs = {
        '1': ([30, 30], [], [('MODEL', 'MODEL')], [MODEL]),
        '2': ([30, 200], [], [('CLIP', 'CLIP')], [ENCODER, 'qwen_image', 'cpu']),
        '3': ([430, 210], [('clip', 'CLIP')] + ([('vae', 'VAE'), ('images.image_1', 'IMAGE')] if reference else []), [('positive', 'CONDITIONING'), ('negative', 'CONDITIONING'), ('latent', 'LATENT')], [text, '', 512]),
        '5': ([440, 650], [], [('LATENT', 'LATENT')], [width, height, 1]),
        '6': ([900, 250], [('model', 'MODEL'), ('positive', 'CONDITIONING'), ('negative', 'CONDITIONING'), ('latent_image', 'LATENT')], [('LATENT', 'LATENT')], [seed, 'fixed', 28, 1.0, 'euler', 'simple', 1.0]),
        '7': ([30, 420], [], [('VAE', 'VAE')], [VAE]),
        '8': ([1320, 220], [('samples', 'LATENT'), ('vae', 'VAE')], [('IMAGE', 'IMAGE')], []),
        '9': ([1740, 220], [('images', 'IMAGE')], [], ['Atelier_Qwen']),
        '10': ([450, 30], [('model', 'MODEL')], [('MODEL', 'MODEL')], ['cpu', 'default']),
        '11': ([30, 650], [], [('IMAGE', 'IMAGE')], [reference]),
    }
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
