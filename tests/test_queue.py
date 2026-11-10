import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'atelier_images'))
from job_queue import JobQueue
from sd_workflow import make_sd_prompt
import server
from monitor import MemoryMonitor


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'queue.json'
        self.calls = []
        self.history = {}
        self.backend = {'queue_running': [], 'queue_pending': []}
        self.factory = lambda job, seed: make_sd_prompt(job['prompt'], 512, 512, seed)
        self.queue = JobQueue(self.path, self.factory, 'http://test')
        self.queue.get = self.get
        self.post = patch('job_queue.requests.post', side_effect=self.submit).start()
        self.addCleanup(patch.stopall)
        self.addCleanup(self.temp.cleanup)

    def get(self, route):
        return self.backend if route == '/queue' else self.history

    def submit(self, url, json, timeout):
        self.calls.append(json)
        self.backend['queue_running'] = [[0, json['prompt_id']]]
        return Mock(ok=True)

    def specs(self, count=1, model='sd'):
        return [{'prompt': 'A red teapot', 'count': count, 'seed': 42, 'model': model, 'format': 'square', 'reference': None}]

    def finish(self):
        pid = self.calls[-1]['prompt_id']
        self.history[pid] = {'status': {'completed': True}, 'outputs': {'9': {'images': [{'filename': pid+'.png', 'type': 'output'}]}}}
        self.backend = {'queue_running': [], 'queue_pending': []}
        self.queue.tick()

    def test_exact_counts_sequential_order_and_seeds(self):
        self.queue.enqueue(self.specs(2, 'flux') + self.specs(1, 'qwen') + self.specs(2, 'sd'))
        for _ in range(5):
            self.queue.tick()
            count = len(self.calls)
            self.queue.tick()
            self.assertEqual(count, len(self.calls), 'No second GPU request while one is running')
            self.finish()
        self.queue.tick()
        self.assertEqual([2, 1, 2], [j['completed'] for j in self.queue.snapshot()['jobs']])
        self.assertEqual([42, 43, 42, 42, 43], [p['prompt']['6']['inputs']['seed'] for p in self.calls])
        self.assertEqual(5, len({p['prompt']['9']['inputs']['filename_prefix'] for p in self.calls}))
        self.assertTrue(all(j['state'] == 'done' for j in self.queue.snapshot()['jobs']))

    def test_pause_cancel_and_resume(self):
        first, second = self.queue.enqueue(self.specs(3) + self.specs())
        self.queue.tick()
        self.queue.control('pause')
        self.queue.control('cancel', first['id'])
        self.finish()
        self.queue.tick()
        self.assertEqual(1, len(self.calls))
        self.assertEqual('cancelled', self.queue.snapshot()['jobs'][0]['state'])
        self.queue.control('resume')
        self.queue.tick()
        self.assertEqual(2, len(self.calls))

    def test_restart_recovers_inflight_without_duplicate(self):
        self.queue.enqueue(self.specs(2))
        self.queue.tick()
        self.queue = JobQueue(self.path, self.factory, 'http://test')
        self.queue.get = self.get
        self.queue.tick()
        self.assertEqual(1, len(self.calls))
        self.finish()
        self.queue.tick()
        self.assertEqual(2, len(self.calls))

    def test_post_timeout_is_reconciled_not_retried(self):
        self.queue.enqueue(self.specs())
        self.post.side_effect = requests.Timeout()
        self.queue.tick()
        self.queue.tick()
        self.assertEqual(1, self.post.call_count)
        self.queue.data['jobs'][0]['attempt']['sent_at'] = time.time() - 61
        self.queue.tick()
        self.assertEqual('error', self.queue.snapshot()['jobs'][0]['state'])
        self.assertEqual(1, self.post.call_count)

    def test_oom_pauses_following_work(self):
        self.queue.enqueue(self.specs(2) + self.specs())
        self.queue.tick()
        pid = self.calls[0]['prompt_id']
        self.history[pid] = {'status': {'status_str': 'error', 'messages': [['execution_error', {'exception_message': 'CUDA out of memory'}]]}}
        self.backend = {'queue_running': [], 'queue_pending': []}
        self.queue.tick()
        self.queue.tick()
        self.assertTrue(self.queue.snapshot()['paused'])
        self.assertEqual(1, len(self.calls))

    def test_backend_busy_waits_and_pending_cancel_never_submits(self):
        job = self.queue.enqueue(self.specs())[0]
        self.backend['queue_running'] = [[0, 'external']]
        self.queue.tick()
        self.assertFalse(self.calls)
        self.queue.control('cancel', job['id'])
        self.backend['queue_running'] = []
        self.queue.tick()
        self.assertFalse(self.calls)

    def test_capacity_and_atomic_enqueue(self):
        self.queue.enqueue(self.specs(200))
        with self.assertRaises(ValueError):
            self.queue.enqueue(self.specs())
        self.assertEqual(1, len(self.queue.snapshot()['jobs']))


class ValidationTests(unittest.TestCase):
    @patch('server.model_info', return_value={'name': 'sd', 'can_edit': False})
    def test_count_and_prompt_validation(self, _):
        for count in (0, 51, -1, True, 1.5, '2'):
            with self.assertRaises(ValueError):
                server.validate_jobs({'prompt': 'test', 'count': count})
        for prompts in ([], [''], ['a'] * 51, 'not a list'):
            with self.assertRaises(ValueError):
                server.validate_jobs({'prompts': prompts})
        specs = server.validate_jobs({'prompts': ['a', 'b'], 'count': 3, 'seed': 12})
        self.assertEqual([3, 3], [s['count'] for s in specs])

    def test_sd_single_image_tiled_decode(self):
        graph = make_sd_prompt('test', 512, 768, 42)['prompt']
        self.assertEqual(1, graph['5']['inputs']['batch_size'])
        self.assertEqual('VAEDecodeTiled', graph['8']['class_type'])
        self.assertEqual(256, graph['8']['inputs']['tile_size'])

    @patch('monitor.subprocess.run', return_value=Mock(stdout='2048, 8192, NVIDIA RTX Test\n'))
    def test_monitor_uses_dedicated_gpu_memory(self, _):
        monitor = MemoryMonitor()
        monitor.sample()
        data = monitor.snapshot()
        self.assertEqual(2 * 1024**3, data['vram']['used'])
        self.assertEqual(8 * 1024**3, data['vram']['total'])
        self.assertGreater(data['ram']['total'], 0)

    @patch('monitor.subprocess.run', side_effect=FileNotFoundError())
    def test_missing_gpu_metrics_are_not_zero(self, _):
        monitor = MemoryMonitor()
        monitor.sample()
        self.assertIsNone(monitor.snapshot()['vram'])


if __name__ == '__main__':
    unittest.main()
