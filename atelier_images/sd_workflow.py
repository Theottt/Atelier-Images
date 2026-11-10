"""Small SD 1.5 pipeline: one latent at a time and tiled VAE decoding."""
MODEL = 'v1-5-pruned-emaonly.safetensors'


def make_sd_prompt(text, width, height, seed):
    graph = {
        '1': {'class_type': 'CheckpointLoaderSimple', 'inputs': {'ckpt_name': MODEL}},
        '3': {'class_type': 'CLIPTextEncode', 'inputs': {'text': text, 'clip': ['1', 1]}},
        '4': {'class_type': 'CLIPTextEncode', 'inputs': {'text': '', 'clip': ['1', 1]}},
        '5': {'class_type': 'EmptyLatentImage', 'inputs': {'width': width, 'height': height, 'batch_size': 1}},
        '6': {'class_type': 'KSampler', 'inputs': {'model': ['1', 0], 'positive': ['3', 0], 'negative': ['4', 0],
              'latent_image': ['5', 0], 'seed': seed, 'steps': 20, 'cfg': 7.0, 'sampler_name': 'euler', 'scheduler': 'normal', 'denoise': 1.0}},
        '8': {'class_type': 'VAEDecodeTiled', 'inputs': {'samples': ['6', 0], 'vae': ['1', 2], 'tile_size': 256, 'overlap': 64, 'temporal_size': 64, 'temporal_overlap': 8}},
        '9': {'class_type': 'SaveImage', 'inputs': {'images': ['8', 0], 'filename_prefix': 'Atelier_SD'}},
    }
    specs = {
        '1': ([], [('MODEL', 'MODEL'), ('CLIP', 'CLIP'), ('VAE', 'VAE')], [MODEL]),
        '3': ([('clip', 'CLIP')], [('CONDITIONING', 'CONDITIONING')], [text]),
        '4': ([('clip', 'CLIP')], [('CONDITIONING', 'CONDITIONING')], ['']),
        '5': ([], [('LATENT', 'LATENT')], [width, height, 1]),
        '6': ([('model', 'MODEL'), ('positive', 'CONDITIONING'), ('negative', 'CONDITIONING'), ('latent_image', 'LATENT')], [('LATENT', 'LATENT')], [seed, 'fixed', 20, 7.0, 'euler', 'normal', 1.0]),
        '8': ([('samples', 'LATENT'), ('vae', 'VAE')], [('IMAGE', 'IMAGE')], [256, 64, 64, 8]),
        '9': ([('images', 'IMAGE')], [], ['Atelier_SD']),
    }
    nodes, links = [], []
    for index, (key, node) in enumerate(graph.items()):
        inputs, outputs, widgets = specs[key]
        nodes.append({'id': int(key), 'type': node['class_type'], 'pos': [(index % 4) * 370, (index // 4) * 330],
                      'size': [340, 260], 'flags': {}, 'order': index, 'mode': 0,
                      'properties': {'Node name for S&R': node['class_type']},
                      'inputs': [{'name': n, 'type': t, 'link': None} for n, t in inputs],
                      'outputs': [{'name': n, 'type': t, 'links': [], 'slot_index': i} for i, (n, t) in enumerate(outputs)],
                      'widgets_values': widgets})
    by_id = {n['id']: n for n in nodes}
    for node in nodes:
        for slot, socket in enumerate(node['inputs']):
            origin, output = graph[str(node['id'])]['inputs'][socket['name']]
            link = len(links) + 1
            socket['link'] = link
            by_id[int(origin)]['outputs'][output]['links'].append(link)
            links.append([link, int(origin), output, node['id'], slot, socket['type']])
    workflow = {'last_node_id': 9, 'last_link_id': len(links), 'nodes': nodes, 'links': links,
                'groups': [], 'config': {}, 'extra': {}, 'version': 0.4}
    return {'prompt': graph, 'extra_data': {'extra_pnginfo': {'workflow': workflow}}}
