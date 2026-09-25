from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
import pandas as pd
from pypdf import PdfReader
from catalog_options import prepare_catalog, whatsapp_number, order_link
from v4_pdf import make_catalog_pdf

def run():
    rows = pd.DataFrame([
        {'id': 2, 'Produit': 'Sac de voyage', 'Categorie': 'Bagagerie', 'Vente': 15000, 'Photo': '', 'Code_barres': ''},
        {'id': 1, 'Produit': 'Écouteurs Bluetooth', 'Categorie': 'Électronique', 'Vente': 10000, 'Photo': '', 'Code_barres': 'ABC-001'},
    ])
    options = {'whatsapp': '77 123 45 67', 'valid_until': (date.today()+timedelta(days=30)).isoformat(), 'promotions': {'2': 12000}}
    prepared = prepare_catalog(rows, options)
    assert list(prepared.Reference) == ['PROD-000002', 'ABC-001']
    assert rows.loc[0, 'Vente'] == 15000
    assert whatsapp_number('+221 77 123 45 67') == '221771234567'
    assert whatsapp_number('00221771234567') == '221771234567'
    assert order_link('771234567').startswith('https://wa.me/221771234567?text=')
    for invalid in (-1, 0, 15000, float('nan'), float('inf')):
        try:
            prepare_catalog(rows, {**options, 'promotions': {'2': invalid}})
        except ValueError:
            pass
        else:
            raise AssertionError(invalid)
    data = make_catalog_pdf(rows, {'shop_name': 'Boutique Sénégal'}, options)
    Path('catalogue-options-test.pdf').write_bytes(data)
    pdf = PdfReader(BytesIO(data))
    text = '\n'.join(p.extract_text() for p in pdf.pages)
    for expected in ('PROD-000002', 'ABC-001', 'PROMO', '12 000 FCFA', '15 000 FCFA', 'Prix valables', 'Bagagerie', 'Électronique'):
        assert expected in text, expected
    links = [a.get_object()['/A']['/URI'] for p in pdf.pages for a in p.get('/Annots', []) if '/A' in a.get_object()]
    assert len(links) == 3 and all(x.startswith('https://wa.me/221771234567') for x in links)
    print('PASS: categories, references, promotional prices, validity and clickable WhatsApp links')

if __name__ == '__main__':
    run()
