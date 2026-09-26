from copy import deepcopy
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
from pypdf import PdfReader
from catalog_library import save_catalog, list_catalogs, restore_catalog
from v4_pdf import make_catalog_pdf


def run():
    products = pd.DataFrame([{'id':1,'Produit':'Sac de voyage','Categorie':'Bagagerie','Vente':19750,'Stock':3,'Photo':''},
                             {'id':2,'Produit':'Chemise','Categorie':'Vêtements','Vente':12650,'Stock':4,'Photo':''}])
    options = {'cover':True,'title':'Collection Samaly Trading','show_prices':False,
               'whatsapp':'771234567','valid_until':(date.today()+timedelta(days=30)).isoformat(),
               'delivery_zones':'Dakar et régions','delivery_fees':'Sur devis','delivery_times':'À confirmer lors de la commande',
               'promotions':{'1':15750}, 'details':{'1':{'Description':'Sac résistant, tissu imperméable. Dimensions : 40 × 25 cm.', 'Tailles':'Unique', 'Couleurs':'Noir, bleu'},
                                                 '2':{'Description':'Coton léger & confortable', 'Tailles':'M, L, XL', 'Couleurs':'Blanc, bleu'}}}
    data = make_catalog_pdf(products, {'shop_name':'Boutique Sénégal','phone':'771234567','address':'Dakar'}, options)
    Path('catalogue-extended-test.pdf').write_bytes(data)
    pdf = PdfReader(BytesIO(data))
    assert len(pdf.pages) >= 2 and 'Samaly Trading' in pdf.pages[0].extract_text()
    text = '\n'.join(p.extract_text() for p in pdf.pages)
    for value in ('Dimensions','M, L, XL','Noir, bleu','Dakar et régions','Sur devis','Conditions de livraison'):
        assert value in text, value
    for value in ('19 750','12 650','15 750','PROMO','Prix valables'):
        assert value not in text, value
    store = {}
    def require_admin(user):
        if user['role'] != 'admin': raise ValueError('Admin required')
    def write(key,value,user):
        require_admin(user)
        store[key] = deepcopy(value)
    features = SimpleNamespace(require_admin=require_admin, read_setting=lambda k,d: deepcopy(store.get(k,d)), write_setting=write)
    user={'id':1,'role':'admin'}
    preset={'product_ids':[1,2,999],'only_stock':True,'options':options}
    with patch.dict('sys.modules', {'business_features':features}):
        save_catalog(user,'Collection',preset)
        saved = list_catalogs(user)['Collection']
        assert saved['options'] == options
        state={'catalog_result':b'old'}
        missing = restore_catalog(state,saved,products)
        assert missing == 1 and state['catalog_products'] == [1,2]
        assert state['catalog_show_prices'] is False and 'catalog_result' not in state
        assert state['catalog_saved_options']['details'] == options['details']
        assert list_catalogs({'id':2,'role':'admin'}) == {}
        try: save_catalog({'id':3,'role':'seller'},'No',preset)
        except ValueError: pass
        else: raise AssertionError('Seller saved a catalogue')
    print('PASS: cover, descriptions, variants, delivery, no product prices, saved catalogues and restore')


if __name__ == '__main__': run()
