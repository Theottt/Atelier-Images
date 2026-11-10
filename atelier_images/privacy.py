"""Targeted application-level deletion; not forensic erasure or remote backup control."""
import json
import re
import sqlite3
from pathlib import Path

import requests
from PIL import Image

PREFIXES = ('Atelier_FLUX', 'Atelier_Qwen', 'Atelier_SD', 'FLUX_Schnell_Test')
DROP = object()


def delete_all(root, queue, comfy):
    """Purge local creative data while idle; never stop processes or erase models."""
    root = root.resolve()
    warnings = []
    deleted = 0
    with queue.work_lock, queue.lock:
        response = requests.get(comfy + '/queue', timeout=10)
        response.raise_for_status()
        backend = response.json()
        if backend.get('queue_running') or backend.get('queue_pending'):
            raise ValueError('Mets la file en pause et attends la fin de la génération en cours, puis réessaie.')
        if any(j.get('attempt') and j['state'] not in ('done', 'error', 'cancelled') for j in queue.data['jobs']):
            raise ValueError('Une génération reste à vérifier. Attends sa synchronisation avant de supprimer.')
        # Resolve and validate every target before any destructive operation.
        directories = [root / p for p in ('ComfyUI/output', 'ComfyUI/input', 'ComfyUI/temp',
                                          'ComfyUI/previews', 'ComfyUI/user/default/workflows')]
        targets = []
        for base in (root / 'ComfyUI', root / 'ComfyUI/user', root / 'ComfyUI/user/default', root / 'atelier_images', root / '.tools'):
            if base.is_symlink() or getattr(base, 'is_junction', lambda: False)() or not base.resolve().is_relative_to(root):
                raise ValueError('Nettoyage refusé : un dossier du projet est redirigé.')
        for directory in directories:
            if not directory.exists():
                continue
            entries = [directory, *directory.rglob('*')]
            for path in entries:
                if path.is_symlink() or getattr(path, 'is_junction', lambda: False)() or not path.resolve().is_relative_to(root):
                    raise ValueError('Nettoyage refusé : un dossier contient un lien vers un autre emplacement.')
                if path.is_file():
                    targets.append(path)
        response = requests.post(comfy + '/history', json={'clear': True}, timeout=10)
        response.raise_for_status()
        queue.data = {'paused': True, 'jobs': [], 'error': ''}
        queue.save()
        for relative in ('atelier_images/active_job.json', 'atelier_images/active_job.tmp',
                         'atelier_images/qwen_verified.json', 'flux_test_job.json', '.tools/queue_live_result.json'):
            path = root / relative
            if path.is_file():
                targets.append(path)
        for path in targets:
            try:
                path.unlink()
                deleted += 1
            except OSError:
                warnings.append('Fichier non supprimé : ' + str(path.relative_to(root)))
        database = root / 'ComfyUI/user/comfyui.db'
        if database.is_symlink():
            warnings.append('Catalogue redirigé : nettoyage refusé.')
        elif database.exists():
            try:
                connection = sqlite3.connect(database, timeout=10)
                try:
                    connection.execute('PRAGMA foreign_keys=ON')
                    connection.execute('PRAGMA secure_delete=ON')
                    with connection:
                        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                        for table in ('asset_tags', 'assets', 'asset_contents', 'tags'):
                            if table in tables:
                                connection.execute('DELETE FROM ' + table)
                    if connection.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0]:
                        warnings.append('Journal SQLite encore utilisé par ComfyUI.')
                finally:
                    connection.close()
            except (sqlite3.Error, OSError):
                warnings.append('Catalogue ComfyUI non entièrement nettoyé.')
        for log in [*root.glob('*.log'), *(root / 'atelier_images').glob('*.log')]:
            try:
                if log.is_symlink():
                    warnings.append('Journal redirigé : ' + log.name)
                    continue
                # Keep open writers' offsets valid; new operational lines may follow.
                with log.open('r+b') as stream:
                    remaining = log.stat().st_size
                    while remaining:
                        size = min(remaining, 65536)
                        stream.write(b' ' * size)
                        remaining -= size
            except OSError:
                warnings.append('Journal non nettoyé : ' + log.name)
    return {'deleted_files': deleted, 'managed_cleanup_complete': not warnings, 'warnings': warnings}


def image_path(output, filename):
    if not isinstance(filename, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+\.png', filename) or not filename.startswith(PREFIXES):
        raise ValueError('Nom d’image invalide.')
    path = output / filename
    if path.is_symlink() or path.resolve().parent != output.resolve():
        raise ValueError('Cette image ne se trouve pas dans le dossier de sortie.')
    return path


def purge_database(database, target):
    if not database.exists():
        return
    connection = sqlite3.connect(database, timeout=10)
    try:
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA secure_delete=ON')
        connection.execute('BEGIN IMMEDIATE')
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'asset_contents', 'assets', 'asset_tags'} <= tables:
            raise RuntimeError('Schéma du catalogue ComfyUI non reconnu.')
        # Compare canonical full paths, never a LIKE on a prompt or basename.
        ids = [cid for cid, path in connection.execute('SELECT id, path FROM asset_contents')
               if Path(path).is_absolute() and Path(path).resolve() == target.resolve()]
        for cid in ids:
            previews = connection.execute('SELECT preview_id FROM assets WHERE content_id=? AND preview_id IS NOT NULL', (cid,)).fetchall()
            if previews:
                raise RuntimeError('Une prévisualisation liée nécessite un nettoyage supplémentaire du catalogue.')
            tags = [r[0] for r in connection.execute('SELECT tag_name FROM asset_tags WHERE asset_id IN (SELECT id FROM assets WHERE content_id=?)', (cid,))] if 'tags' in tables else []
            connection.execute('DELETE FROM asset_tags WHERE asset_id IN (SELECT id FROM assets WHERE content_id=?)', (cid,))
            connection.execute('DELETE FROM assets WHERE content_id=?', (cid,))
            connection.execute('DELETE FROM asset_contents WHERE id=?', (cid,))
            for tag in tags:
                connection.execute('DELETE FROM tags WHERE name=? AND NOT EXISTS (SELECT 1 FROM asset_tags WHERE tag_name=?)', (tag, tag))
        connection.commit()
        # This limits WAL remnants when possible, but is not a secure disk wipe.
        if connection.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0]:
            raise RuntimeError('Catalogue nettoyé, mais le journal WAL est encore utilisé par ComfyUI.')
    finally:
        connection.close()


def scrub_json(value, filename, history_ids):
    """Remove matching records while keeping sibling images and their shared prompt."""
    if isinstance(value, dict):
        if value.get('filename') == filename or value.get('id') in history_ids:
            return DROP
        if isinstance(value.get('images'), list) and filename in value['images']:
            remaining = [x for x in value['images'] if x != filename]
            if not remaining:
                return DROP
            value = {**value, 'images': remaining}
        return {k: cleaned for k, v in value.items() if (cleaned := scrub_json(v, filename, history_ids)) is not DROP}
    if isinstance(value, list):
        return [cleaned for v in value if (cleaned := scrub_json(v, filename, history_ids)) is not DROP]
    return DROP if value == filename else value


def delete_image(root, queue, comfy, filename):
    output = root / 'ComfyUI/output'
    target = image_path(output, filename)
    if not target.is_file():
        raise ValueError('Cette image est introuvable.')
    with Image.open(target) as image:
        graph = json.loads(image.info.get('prompt', '{}'))
    prompt = graph.get('3', {}).get('inputs', {}).get('text', graph.get('3', {}).get('inputs', {}).get('prompt', ''))
    warnings, history_ids = [], []
    with queue.work_lock, queue.lock:
        if any(filename in j['images'] and j['state'] not in ('done', 'error', 'cancelled') for j in queue.data['jobs']):
            raise ValueError('Attends la fin de cette série, ou annule ses images restantes avant de supprimer celle-ci.')
        # Require a live backend: no false claim that unavailable history was purged.
        response = requests.get(comfy + '/history', timeout=10)
        response.raise_for_status()
        for pid, entry in response.json().items():
            images = [i for out in entry.get('outputs', {}).values() for i in out.get('images', [])]
            matches = [i for i in images if i.get('filename') == filename and i.get('type') == 'output' and not i.get('subfolder')]
            if matches:
                if len(matches) == len(images):
                    history_ids.append(pid)
                else:
                    warnings.append('Un historique ComfyUI partagé avec d’autres images a été conservé.')
        if history_ids:
            response = requests.post(comfy + '/history', json={'delete': history_ids}, timeout=10)
            response.raise_for_status()
        # The file contains its own prompt/workflow metadata. Unlink bypasses the Recycle Bin.
        target.unlink()
        for job in list(queue.data['jobs']):
            if filename in job['images']:
                job['images'].remove(filename)
                if not job['images']:
                    queue.data['jobs'].remove(job)
        try:
            queue.save()
        except OSError:
            warnings.append('État de la file non nettoyé sur disque.')
        for relative in ('atelier_images/active_job.json', 'atelier_images/qwen_verified.json', 'flux_test_job.json', '.tools/queue_live_result.json'):
            path = root / relative
            try:
                if path.exists():
                    original = json.loads(path.read_text(encoding='utf-8'))
                    cleaned = scrub_json(original, filename, history_ids)
                    if cleaned != original:
                        if cleaned is DROP:
                            path.unlink()
                        else:
                            path.write_text(json.dumps(cleaned, ensure_ascii=False), encoding='utf-8')
            except (OSError, ValueError):
                warnings.append('État local non nettoyé : ' + path.name)
        try:
            purge_database(root / 'ComfyUI/user/comfyui.db', target)
        except (sqlite3.Error, OSError, RuntimeError):
            warnings.append('Catalogue ComfyUI ou journal WAL non entièrement nettoyé.')
        # Remove only attributable log lines. Shared prompts remain in other images/records.
        tokens = {filename}
        if prompt:
            tokens.update((prompt, json.dumps(prompt, ensure_ascii=True)[1:-1], json.dumps(prompt, ensure_ascii=False)[1:-1]))
        for log in [*root.glob('*.log'), *(root / 'atelier_images').glob('*.log')]:
            try:
                text = log.read_bytes()
                cleaned = text
                for token in sorted(tokens, key=len, reverse=True):
                    for encoding in ('utf-8', 'cp1252'):
                        try:
                            encoded = token.encode(encoding)
                            replacement = b'[deleted]'.ljust(len(encoded), b' ') if len(encoded) >= 9 else b'*' * len(encoded)
                            cleaned = cleaned.replace(encoded, replacement)
                        except UnicodeEncodeError:
                            pass
                if cleaned != text:
                    # Fixed-length overwrites preserve live writer offsets and appended events.
                    with log.open('r+b') as stream:
                        stream.write(cleaned)
            except OSError:
                warnings.append('Journal non nettoyé : ' + log.name)
    return {'deleted': True, 'managed_cleanup_complete': not warnings, 'warnings': warnings}
