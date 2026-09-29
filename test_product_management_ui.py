"""Test the real Streamlit controls with an isolated database."""
from pathlib import Path
from tempfile import TemporaryDirectory
import gc
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import db
import cloud_db


def run():
    old_path = db.DB_PATH
    with TemporaryDirectory() as folder, patch.object(cloud_db, 'enabled', return_value=False):
        db.DB_PATH = Path(folder) / 'ui.db'
        db.init_db()
        db.add_product('Premier', '', 100, 200, 5, 1, None)
        db.add_product('Second', '', 100, 200, 5, 1, None)
        source = '''
import streamlit as st
import db
from product_management_ui import deletion_panel
deletion_panel(st.session_state.get('actor', {'id':1,'role':'admin'}), db.products())
'''
        at = AppTest.from_string(source).run()
        assert not at.exception
        assert at.button[0].disabled
        at.text_input[0].set_value('Doublon').run()
        assert at.button[0].disabled
        at.checkbox[0].check().run()
        assert not at.button[0].disabled
        at.selectbox[0].select(2).run()
        assert not at.checkbox[0].value and at.button[0].disabled
        at.text_input[0].set_value('Erreur de saisie').run()
        at.checkbox[0].check().run()
        at.button[0].click().run()
        assert not at.exception and at.success
        assert list(db.products().Produit) == ['Premier']
        # A newly displayed stock quantity always needs a new confirmation.
        at.text_input[0].set_value('Doublon').run()
        at.checkbox[0].check().run()
        db.set_stock(1, 4)
        at.run()
        assert not at.checkbox[0].value and at.button[0].disabled
        # Preserve a linked product and show the reason to the admin.
        db.execute('INSERT INTO sale_items(sale_id,product_id,quantity,unit_price) VALUES(1,1,1,200)')
        at.text_input[0].set_value('Doublon').run()
        at.checkbox[0].check().run()
        at.button[0].click().run()
        assert not at.exception and at.error and len(db.products()) == 1
        # Last product deletion still shows success after the inventory is empty.
        db.execute('DELETE FROM sale_items')
        at.button[0].click().run()
        assert not at.exception and at.success and not at.button
        assert db.products().empty
        seller = AppTest.from_string(source)
        seller.session_state['actor'] = {'id':2,'role':'seller'}
        seller.run()
        assert not seller.exception and not seller.button and not seller.selectbox
        db.DB_PATH = old_path
        gc.collect()
    print('PASS: confirmation, product/stock changes, history protection, last product, seller restriction')


if __name__ == '__main__':
    run()
