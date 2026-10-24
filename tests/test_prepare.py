import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_atelier


class PrepareTests(unittest.TestCase):
    def test_install_and_repeat_preserve_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loader = root / 'ComfyUI/custom_nodes/ComfyUI-GGUF/loader.py'
            loader.parent.mkdir(parents=True)
            (root / 'ComfyUI/main.py').touch()
            original = 'IMG_ARCH_LIST = {"flux", "qwen_image",}\n'
            loader.write_text(original, encoding='utf-8')
            source = root / 'atelier_images/integration/atelier_reference.py'
            source.parent.mkdir(parents=True)
            source.write_text('# reference node\n', encoding='utf-8')
            with patch.object(prepare_atelier, 'ROOT', root):
                prepare_atelier.main()
                first = loader.read_text(encoding='utf-8')
                prepare_atelier.main()
            scope = {}
            exec(first, scope)
            self.assertIn('qwen_image21', scope['IMG_ARCH_LIST'])
            self.assertEqual(first, loader.read_text(encoding='utf-8'))
            self.assertEqual(original, loader.with_suffix('.py.atelier.bak').read_text(encoding='utf-8'))
            self.assertEqual(source.read_bytes(), (root / 'ComfyUI/custom_nodes/atelier_reference.py').read_bytes())

    def test_unknown_loader_is_not_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            loader = root / 'ComfyUI/custom_nodes/ComfyUI-GGUF/loader.py'
            loader.parent.mkdir(parents=True)
            (root / 'ComfyUI/main.py').touch()
            loader.write_text('# different loader\n', encoding='utf-8')
            with patch.object(prepare_atelier, 'ROOT', root):
                with self.assertRaisesRegex(RuntimeError, 'layout changed'):
                    prepare_atelier.main()
            self.assertEqual('# different loader\n', loader.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
