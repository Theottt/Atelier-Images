"""Global dedicated NVIDIA memory and physical system RAM; no network calls."""
import copy
import csv
import io
import subprocess
import threading
import time

import psutil


class MemoryMonitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.value = {'sampled_at': None, 'vram': None, 'ram': None}

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.value)

    def sample(self):
        result = {'sampled_at': time.time(), 'vram': None, 'ram': None}
        try:
            ram = psutil.virtual_memory()
            result['ram'] = {'used': ram.total - ram.available, 'total': ram.total}
        except (OSError, RuntimeError):
            pass
        try:
            output = subprocess.run(['nvidia-smi', '--id=0', '--query-gpu=memory.used,memory.total,name',
                                     '--format=csv,noheader,nounits'], capture_output=True, text=True,
                                    timeout=3, check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            used, total, name = next(csv.reader(io.StringIO(output.stdout)))
            result['vram'] = {'used': int(used.strip()) * 1024**2, 'total': int(total.strip()) * 1024**2,
                              'name': name.strip(), 'limit': 8 * 1024**3}
        except (OSError, ValueError, StopIteration, subprocess.SubprocessError):
            pass
        with self.lock:
            self.value = result

    def run(self, stop):
        while not stop.is_set():
            self.sample()
            stop.wait(2)
