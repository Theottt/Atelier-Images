import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from PIL import Image, PngImagePlugin

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'atelier_images'))
from job_queue import JobQueue
from privacy import delete_image, image_path, scrub_json
import server


class DeleteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / 'ComfyUI/output'
        self.output.mkdir(parents=True)
        (self.root / 'atelier_images').mkdir()
        (self.root / 'ComfyUI/user').mkdir()
        self.name = 'Atelier_SD_delete_test.png'
        self.other = 'Atelier_SD_keep_test.png'
        self.prompt = 'A private test prompt shared by two images'
        meta = PngImagePlugin.PngInfo()
        meta.add_text('prompt', json.dumps({'3': {'inputs': {'text': self.prompt}}}))
        for name in (self.name, self.other):
            Image.new('RGB', (8, 8), 'red').save(self.output / name, pnginfo=meta)
        self.other_bytes = (self.output / self.other).read_bytes()
        self.queue = JobQueue(self.root / 'atelier_images/queue_state.json', None, 'http://test')
        self.queue.data['jobs'] = [{'id':'group', 'prompt':self.prompt, 'state':'done', 'count':2, 'completed':2,
                                   'images':[self.name, self.other], 'attempt':None}]
        self.queue.save()
        self.history = {'selected': {'outputs': {'9': {'images': [{'filename':self.name, 'type':'output', 'subfolder':''}]}}},
                        'other': {'outputs': {'9': {'images': [{'filename':self.other, 'type':'output', 'subfolder':''}]}}}}
        self.get = patch('privacy.requests.get', return_value=Mock(json=lambda:self.history)).start()
        self.post = patch('privacy.requests.post', return_value=Mock()).start()
        self.addCleanup(patch.stopall)
        self.db = self.root / 'ComfyUI/user/comfyui.db'
        with closing(sqlite3.connect(self.db)) as c:
            c.executescript('CREATE TABLE asset_contents(id TEXT PRIMARY KEY,path TEXT); CREATE TABLE assets(id TEXT,content_id TEXT,preview_id TEXT); CREATE TABLE asset_tags(asset_id TEXT,tag_name TEXT); CREATE TABLE tags(name TEXT);')
            for name in (self.name,self.other):
                c.execute('INSERT INTO asset_contents VALUES (?,?)', (name,str((self.output/name).resolve())))
                c.execute('INSERT INTO assets VALUES (?,?,NULL)', (name,name))
                c.execute('INSERT INTO asset_tags VALUES (?,?)', (name,name))
                c.execute('INSERT INTO tags VALUES (?)', (name,))
            c.commit()

    def test_targeted_delete_keeps_sibling_prompt_and_rows(self):
        log = self.root/'atelier_images/test.log'
        log.write_text(self.name+'\n'+self.prompt+'\nKeep this unrelated event\n',encoding='utf-8')
        log_size = log.stat().st_size
        result = delete_image(self.root,self.queue,'http://test',self.name)
        self.assertTrue(result['managed_cleanup_complete'], result)
        self.assertFalse((self.output/self.name).exists())
        self.assertEqual(self.other_bytes,(self.output/self.other).read_bytes())
        self.assertEqual([self.other], self.queue.data['jobs'][0]['images'])
        self.assertEqual(self.prompt, self.queue.data['jobs'][0]['prompt'])
        self.assertNotIn(self.name,log.read_text(encoding='utf-8'))
        self.assertNotIn(self.prompt,log.read_text(encoding='utf-8'))
        self.assertIn('Keep this unrelated event',log.read_text(encoding='utf-8'))
        self.assertEqual(log_size, log.stat().st_size)
        self.assertEqual({'delete':['selected']},self.post.call_args.kwargs['json'])
        with closing(sqlite3.connect(self.db)) as c:
            self.assertEqual([(self.other,)],c.execute('SELECT id FROM asset_contents').fetchall())
            self.assertEqual([(self.other,)],c.execute('SELECT id FROM assets').fetchall())
            self.assertEqual([(self.other,)],c.execute('SELECT name FROM tags').fetchall())

    def test_final_image_removes_queue_prompt_and_legacy_record(self):
        self.queue.data['jobs'][0]['images']=[self.name]
        path=self.root/'atelier_images/active_job.json'
        path.write_text(json.dumps({'id':'selected','prompt':self.prompt,'images':[self.name]}),encoding='utf-8')
        delete_image(self.root,self.queue,'http://test',self.name)
        self.assertFalse(path.exists())
        self.assertFalse(self.queue.data['jobs'])

    def test_unavailable_history_leaves_file_untouched(self):
        self.get.side_effect=requests.ConnectionError()
        with self.assertRaises(requests.ConnectionError):
            delete_image(self.root,self.queue,'http://test',self.name)
        self.assertTrue((self.output/self.name).exists())

    def test_active_series_is_not_modified(self):
        self.queue.data['jobs'][0]['state']='running'
        with self.assertRaises(ValueError):
            delete_image(self.root,self.queue,'http://test',self.name)
        self.assertTrue((self.output/self.name).exists())
        self.get.assert_not_called()

    def test_shared_history_is_reported_not_silently_removed(self):
        self.history['selected']['outputs']['9']['images'].append({'filename':self.other,'type':'output'})
        result=delete_image(self.root,self.queue,'http://test',self.name)
        self.assertFalse(result['managed_cleanup_complete'])
        self.post.assert_not_called()

    @patch('privacy.purge_database',side_effect=sqlite3.OperationalError('locked'))
    def test_partial_cleanup_is_explicit(self,_):
        result=delete_image(self.root,self.queue,'http://test',self.name)
        self.assertTrue(result['deleted'])
        self.assertFalse(result['managed_cleanup_complete'])
        self.assertTrue(result['warnings'])

    def test_paths_and_unrelated_null_fields(self):
        for name in ('../Atelier_SD_test.png','Atelier_SD_test.png:stream','other.png','Atelier_SD_/test.png'):
            with self.assertRaises(ValueError): image_path(self.output,name)
        payload={'reference':None,'images':[self.other],'prompt':self.prompt}
        self.assertEqual(payload,scrub_json(payload,self.name,[]))


class LongPromptTests(unittest.TestCase):
    def test_only_one_server_can_bind_the_port(self):
        first = server.AtelierHTTPServer(('127.0.0.1', 0), server.Handler)
        try:
            with self.assertRaises(OSError):
                server.AtelierHTTPServer(first.server_address, server.Handler)
        finally:
            first.server_close()

    @patch('server.model_info',return_value={'name':'sd','can_edit':False})
    def test_limits_are_per_prompt_and_total(self,_):
        text='a'*100000
        self.assertEqual(text,server.validate_jobs({'prompt':text})[0]['prompt'])
        self.assertEqual(10,len(server.validate_jobs({'prompts':[text]*10})))
        for data in ({'prompt':text+'a'},{'prompts':[text]*11}):
            with self.assertRaises(ValueError): server.validate_jobs(data)


if __name__=='__main__': unittest.main()
