import json
from pathlib import Path
import re


def test_translation_catalogs_and_interpolation():
    source = Path(__file__).resolve().parents[1] / 'server' / 'web' / 'locales.js'
    catalogs = json.loads(source.read_text().split(' = ', 1)[1].strip().removesuffix(';'))
    assert set(catalogs) == {'es', 'en', 'fr', 'de', 'it', 'pt'}
    for language, entries in catalogs.items():
        assert entries.keys() == catalogs['es'].keys(), language
        for key, text in entries.items():
            assert text.strip(), (language, key)
            assert set(re.findall(r'\{\w+\}', key)) == set(re.findall(r'\{\w+\}', text)), (language, key)
