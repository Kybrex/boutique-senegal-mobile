from base64 import b64encode
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from PIL import Image
from pypdf import PdfReader
from v4_pdf import _catalog_photo, make_catalog_pdf


def run():
    raw = BytesIO()
    Image.new('RGB', (640, 240), '#dcb456').save(raw, 'PNG')
    uri = 'data:image/png;base64,' + b64encode(raw.getvalue()).decode()
    assert _catalog_photo(uri)
    for bad in ('', None, float('nan'), 'data:image/png;base64,broken', 'file:///secret'):
        assert _catalog_photo(bad) is None
    with patch('urllib.request.urlopen', return_value=BytesIO(raw.getvalue())):
        assert _catalog_photo('https://example.test/photo.png')
    with patch('urllib.request.urlopen', side_effect=TimeoutError):
        assert _catalog_photo('https://example.test/missing.png') is None
    rows = [{'Produit': f'Produit {i} - Sac élégant & accessoires', 'Categorie': 'Collection été',
             'Vente': 12500, 'Photo': uri if i % 2 else ''} for i in range(9)]
    data = make_catalog_pdf(pd.DataFrame(rows), {'shop_name': 'Boutique Sénégal', 'phone': '77 000 00 00'})
    Path('catalogue-test.pdf').write_bytes(data)
    pdf = PdfReader(BytesIO(data))
    text = '\n'.join(page.extract_text() for page in pdf.pages)
    assert len(pdf.pages) > 1
    assert all(f'Produit {i}' in text for i in range(9))
    assert 'Photo indisponible' in text and '12 500 FCFA' in text
    assert any(len(page.images) > 1 for page in pdf.pages)
    assert PdfReader(BytesIO(make_catalog_pdf(pd.DataFrame()))).pages
    print('PASS: embedded photos, remote photos, missing/corrupt photos, pagination and empty catalog')


if __name__ == '__main__':
    run()
