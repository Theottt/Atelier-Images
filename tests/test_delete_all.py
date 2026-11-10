import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'atelier_images'))
from job_queue import JobQueue
from privacy import delete_all


class DeleteAllTests(unittest.TestCase):
    def test_purge_preserves_models_and_clears_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = ['ComfyUI/output/example.png', 'ComfyUI/input/reference.png',
                     'ComfyUI/user/default/workflows/personal.json',
                     'atelier_images/active_job.json', 'atelier_images/app.log',
                     'ComfyUI/models/model.gguf']
            for name in files:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('private test data')
            db = root / 'ComfyUI/user/comfyui.db'
            with closing(sqlite3.connect(db)) as connection:
                connection.execute('CREATE TABLE assets (id TEXT)')
                connection.execute("INSERT INTO assets VALUES ('private')")
                connection.commit()
            queue = JobQueue(root / 'atelier_images/queue_state.json', None, 'http://test')
            queue.data['jobs'] = [{'state': 'queued', 'prompt': 'private'}]
            response = Mock()
            response.json.return_value = {'queue_running': [], 'queue_pending': []}
            with patch('privacy.requests.get', return_value=response), patch('privacy.requests.post', return_value=response) as post:
                result = delete_all(root, queue, 'http://test')
            self.assertTrue(result['managed_cleanup_complete'])
            self.assertTrue((root / files[-1]).exists())
            for name in files[:4]:
                self.assertFalse((root / name).exists())
            self.assertNotIn('private', (root / 'atelier_images/app.log').read_text())
            self.assertEqual(json.loads(queue.path.read_text())['jobs'], [])
            with closing(sqlite3.connect(db)) as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM assets').fetchone()[0], 0)
            post.assert_called_once_with('http://test/history', json={'clear': True}, timeout=10)

    def test_running_backend_prevents_deletion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = JobQueue(root / 'queue.json', None, 'http://test')
            response = Mock()
            response.json.return_value = {'queue_running': [[1]], 'queue_pending': []}
            with patch('privacy.requests.get', return_value=response), patch('privacy.requests.post') as post:
                with self.assertRaises(ValueError):
                    delete_all(root, queue, 'http://test')
                post.assert_not_called()
            self.assertFalse(queue.path.exists())


if __name__ == '__main__':
    unittest.main()
