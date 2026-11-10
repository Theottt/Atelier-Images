"""Character sheets: write @Name in a prompt to reuse the same description (and reference image) every time.

Sheets live in atelier_images/characters/characters.json (personal data, ignored by Git):
    {"BeanBlob": {"label": "Bean Blob", "description": "a round pink bean-shaped blob ...", "reference": "BeanBlob.png"}}
The optional reference PNG sits next to the JSON file. With Qwen, references guide the image;
with FLUX or Stable Diffusion only the text description is inserted.
"""
import json
import re
import shutil
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
LIBRARY = HERE / 'characters'
SHEETS = LIBRARY / 'characters.json'
TOKEN = re.compile(r'@([A-Za-z][A-Za-z0-9_]{0,40})')
NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,40}')
MAX_REFERENCES = 4


def load(path=SHEETS):
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('characters.json doit contenir un objet {"Nom": {...}}.')
    return {name: sheet for name, sheet in data.items() if NAME.fullmatch(name) and isinstance(sheet, dict)
            and isinstance(sheet.get('description'), str) and sheet['description'].strip()}


def listing(path=SHEETS):
    library = path.parent
    return [{'name': name, 'label': sheet.get('label') or name, 'description': sheet['description'],
             'reference': bool(sheet.get('reference')) and (library / sheet['reference']).is_file()}
            for name, sheet in sorted(load(path).items())]


def expand(text, path=SHEETS):
    """Return (expanded text, [reference file paths], [unknown names]). Each character is described once."""
    sheets = load(path)
    seen, references, unknown = [], [], []

    def replace(match):
        name = match.group(1)
        sheet = sheets.get(name)
        if not sheet:
            unknown.append(name)
            return match.group(0)
        label = sheet.get('label') or name
        if name in seen:
            return label
        seen.append(name)
        reference = sheet.get('reference')
        file = path.parent / reference if isinstance(reference, str) and '/' not in reference and '\\' not in reference else None
        if file and file.is_file() and file.suffix.lower() == '.png' and len(references) < MAX_REFERENCES:
            references.append(file)
            return f'{label} (exactly the character of reference image {len(references)}: {sheet["description"].strip()})'
        return f'{label} ({sheet["description"].strip()})'

    return TOKEN.sub(replace, text), references, unknown


def stage(references, input_dir):
    """Copy reference sheets into ComfyUI/input under the name the reference loader accepts."""
    names = []
    input_dir.mkdir(parents=True, exist_ok=True)
    for file in references:
        name = 'atelier_ref_char_' + file.stem + '.png'
        target = input_dir / name
        if not target.is_file() or target.stat().st_mtime < file.stat().st_mtime:
            shutil.copy2(file, target)
        names.append(name)
    return names


def save_reference(name, image_path, path=SHEETS):
    """Use a gallery image as the reference sheet of an existing character."""
    sheets = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    if not NAME.fullmatch(name or '') or name not in sheets:
        raise ValueError('Fiche inconnue : ajoute-la d’abord dans characters.json.')
    with Image.open(image_path) as source:
        source.convert('RGB').save(path.parent / f'{name}.png')
    sheets[name]['reference'] = f'{name}.png'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(sheets, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)
