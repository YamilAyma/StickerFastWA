import hashlib
import json
from pathlib import Path
from PIL import ImageFont


def test_bundled_google_fonts_and_licenses():
    root=Path(__file__).resolve().parents[1]/'server'/'web'/'fonts'
    catalog=json.loads((root/'catalog.json').read_text())
    assert len(catalog)>=30
    assert len({font['id'] for font in catalog})==len(catalog)
    assert len({font['category'] for font in catalog})>=6
    for font in catalog:
        file=root/(font['id']+'.ttf')
        assert font['url']=='/web/fonts/'+file.name
        assert hashlib.sha256(file.read_bytes()).hexdigest()==font['sha256']
        license=(root/(font['id']+'-OFL.txt')).read_text()
        assert 'SIL OPEN FONT LICENSE' in license
        assert ImageFont.truetype(str(file),32).getlength('Hola, Perú!')>0
