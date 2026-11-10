import io
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server
import models
from qwen_workflow import make_qwen_prompt, MODEL


class WorkflowTests(unittest.TestCase):
    def test_memory_profile_rejects_forced_cpu_encoder(self):
        flags = ['--disable-dynamic-vram', '--reserve-vram', '1']
        with patch('server.requests.get') as get:
            get.return_value.json.return_value = {'system': {'argv': flags}}
            self.assertEqual(server.comfy_status(), (True, True))
            get.return_value.json.return_value = {'system': {'argv': flags + ['--lowvram']}}
            self.assertEqual(server.comfy_status(), (True, False))

    def check_links(self, payload):
        workflow = payload['extra_data']['extra_pnginfo']['workflow']
        by_id = {n['id']: n for n in workflow['nodes']}
        for link_id, origin, slot, dest, dest_slot, kind in workflow['links']:
            self.assertIn(link_id, by_id[origin]['outputs'][slot]['links'])
            self.assertEqual(by_id[dest]['inputs'][dest_slot]['link'], link_id)

    def test_flux_preserved(self):
        for variant, steps in [('schnell', 4), ('dev', 20)]:
            payload = server.make_prompt('Un lac', 'portrait', 123, {'name': 'selected.gguf', 'variant': variant, 'steps': steps})
            self.check_links(payload)
            self.assertEqual(payload['prompt']['1']['inputs']['unet_name'], 'selected.gguf')
            self.assertEqual(payload['prompt']['6']['inputs']['steps'], steps)

    def test_qwen_generation(self):
        payload = make_qwen_prompt('Un lac', 768, 512, 42)
        self.check_links(payload)
        graph = payload['prompt']
        self.assertEqual(graph['1']['inputs']['unet_name'], MODEL)
        self.assertEqual(graph['2']['inputs']['type'], 'qwen_image')
        self.assertEqual(graph['2']['inputs']['device'], 'default')
        clip_node = next(n for n in payload['extra_data']['extra_pnginfo']['workflow']['nodes'] if n['id'] == 2)
        self.assertEqual(clip_node['widgets_values'][-1], 'default')
        self.assertEqual(graph['6']['inputs']['steps'], 28)
        self.assertEqual(graph['6']['inputs']['latent_image'], ['5', 0])
        self.assertEqual(graph['5']['inputs']['width'], 768)

    def test_qwen_edit(self):
        payload = make_qwen_prompt('Change le ciel', 512, 512, 42, 'atelier_ref_test.png')
        self.check_links(payload)
        graph = payload['prompt']
        self.assertEqual(graph['3']['inputs']['images.image_1'], ['11', 0])
        self.assertEqual(graph['3']['inputs']['vae'], ['7', 0])
        self.assertEqual(graph['6']['inputs']['latent_image'], ['3', 2])
        self.assertNotIn('5', graph)

    def test_paths(self):
        for name in ['../x.gguf', 'C:\\x.gguf', 'x.gguf:stream', 'CON.gguf']:
            with self.assertRaises(ValueError):
                models.model_path(name)


class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.url = f'http://127.0.0.1:{cls.httpd.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def post(self, route, data, **headers):
        return requests.post(self.url + route, data=data, headers={'Host': '127.0.0.1:8189', **headers}, timeout=5)

    def test_model_upload_removed(self):
        self.assertEqual(self.post('/api/models/upload', b'GGUF').status_code, 404)
        self.assertEqual(self.post('/api/models/check', b'{}').status_code, 404)

    def test_reference_normalized(self):
        buffer = io.BytesIO()
        Image.new('RGB', (1600, 800), 'blue').save(buffer, format='JPEG')
        with tempfile.TemporaryDirectory() as directory, patch('server.ROOT', Path(directory)):
            response = self.post('/api/reference', buffer.getvalue())
            self.assertEqual(response.status_code, 201, response.text)
            info = response.json()
            self.assertEqual((info['width'], info['height']), (1536, 768))
            with Image.open(Path(directory) / 'ComfyUI/input' / info['name']) as image:
                self.assertEqual(image.format, 'PNG')

    def test_invalid_reference(self):
        self.assertEqual(self.post('/api/reference', b'not an image').status_code, 400)
        self.assertEqual(self.post('/api/reference', b'', Origin='https://example.com').status_code, 403)


if __name__ == '__main__':
    unittest.main()


class LightningAndSheetsTests(unittest.TestCase):
    def check_links(self, payload):
        WorkflowTests.check_links(self, payload)

    def test_qwen_fast_uses_lora_and_published_sigmas(self):
        from qwen_workflow import LIGHTNING_LORA, LIGHTNING_SIGMAS
        payload = make_qwen_prompt('Un lac', 512, 512, 7, fast=True)
        self.check_links(payload)
        graph = payload['prompt']
        self.assertEqual(graph['12']['inputs']['lora_name'], LIGHTNING_LORA)
        self.assertEqual(graph['10']['inputs']['model'], ['12', 0])
        self.assertEqual(graph['6']['class_type'], 'SamplerCustom')
        self.assertEqual(graph['6']['inputs']['noise_seed'], 7)
        self.assertEqual(graph['14']['inputs']['sigmas'], LIGHTNING_SIGMAS)
        self.assertTrue(graph['9']['inputs']['filename_prefix'].startswith('Atelier_Qwen'))

    def test_character_references_keep_chosen_format(self):
        payload = make_qwen_prompt('Scene', 768, 512, 7, fast=True, references=['atelier_ref_char_A.png', 'atelier_ref_char_B.png'])
        self.check_links(payload)
        graph = payload['prompt']
        self.assertEqual(graph['3']['inputs']['images.image_1'], ['20', 0])
        self.assertEqual(graph['3']['inputs']['images.image_2'], ['21', 0])
        self.assertEqual(graph['6']['inputs']['latent_image'], ['5', 0])
        self.assertEqual(graph['5']['inputs']['width'], 768)

    def test_sheet_expansion(self):
        import json
        import characters
        with tempfile.TemporaryDirectory() as folder:
            sheets = Path(folder) / 'characters.json'
            Image.new('RGB', (8, 8)).save(Path(folder) / 'Blob.png')
            sheets.write_text(json.dumps({'Blob': {'label': 'Bean Blob', 'description': 'pink blob', 'reference': 'Blob.png'},
                                          'Pup': {'description': 'blue pup'}}), encoding='utf-8')
            text, refs, unknown = characters.expand('@Blob plays with @Pup and @Blob and @Nope', sheets)
            self.assertIn('Bean Blob (exactly the character of reference image 1: pink blob)', text)
            self.assertIn('Pup (blue pup)', text)
            self.assertEqual(text.count('pink blob'), 1)
            self.assertEqual([r.name for r in refs], ['Blob.png'])
            self.assertEqual(unknown, ['Nope'])
            staged = characters.stage(refs, Path(folder) / 'input')
            self.assertEqual(staged, ['atelier_ref_char_Blob.png'])
