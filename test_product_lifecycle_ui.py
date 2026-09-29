from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import gc
import unittest
from streamlit.testing.v1 import AppTest
import db
import cloud_db

SOURCE='''
import streamlit as st
import db
import product_lifecycle_ui as ui
user=st.session_state.get('user',{'id':1,'role':'admin'})
ui.notice()
ui.creation_panel(user,db.suppliers())
ui.management_panel(user)
ui.stock_panel(user,db.products())
'''


def widget(elements,label):
    return next(item for item in elements if item.label==label)


class LifecycleUiTests(unittest.TestCase):
    def setUp(self):
        self.folder=TemporaryDirectory()
        self.old_path=db.DB_PATH
        db.DB_PATH=Path(self.folder.name)/'ui.db'
        self.mock=patch.object(cloud_db,'enabled',return_value=False); self.mock.start()
        db.init_db(); db.add_product('Café noir','Boissons',100,200,10,2,None)
        self.app=AppTest.from_string(SOURCE,default_timeout=15).run()
        self.assertFalse(self.app.exception)
    def tearDown(self):
        db.DB_PATH=self.old_path; self.mock.stop(); gc.collect(); self.folder.cleanup()
    def test_archive_restore_last_product(self):
        at=self.app
        self.assertTrue(widget(at.button,'Archiver le produit').disabled)
        widget(at.text_input,'Motif d’archivage').set_value('Fin de gamme').run()
        widget(at.checkbox,'Je confirme l’archivage').check().run()
        widget(at.button,'Archiver le produit').click().run()
        self.assertFalse(at.exception); self.assertTrue(at.success)
        self.assertTrue(db.products().empty)
        widget(at.radio,'Afficher').set_value('Produits archivés').run()
        widget(at.text_input,'Motif de restauration').set_value('Reprise').run()
        widget(at.checkbox,'Je confirme la restauration').check().run()
        widget(at.button,'Restaurer le produit').click().run()
        self.assertFalse(at.exception); self.assertEqual(int(db.products().iloc[0].Stock),10)
    def test_identity_form_and_duplicate_warning(self):
        at=self.app
        widget(at.text_input,'Nouveau nom').set_value('Café premium')
        widget(at.text_input,'Nouvelle catégorie').set_value('Épicerie')
        widget(at.button,'Enregistrer la fiche').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(db.products().iloc[0].Produit,'Café premium')
        widget(at.text_input,'Nom du nouveau produit').set_value(' CAFE  PREMIUM ').run()
        self.assertTrue(at.warning)
        self.assertTrue(widget(at.button,'Ajouter le produit').disabled)
    def test_loss_reason_history_and_export(self):
        at=self.app
        widget(at.segmented_control,'Modification').set_value('Retirer').run()
        widget(at.number_input,'Quantité').set_value(3).run()
        widget(at.selectbox,'Motif de sortie').select('Perte').run()
        widget(at.text_input,'Précision du mouvement').set_value('Produit égaré').run()
        widget(at.button,'Enregistrer le stock').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(int(db.products().iloc[0].Stock),7)
        widget(at.button,'Afficher / actualiser l’historique').click().run()
        self.assertFalse(at.exception)
        frame=at.dataframe[0].value
        self.assertIn('Sortie',list(frame['Événement']))
        self.assertTrue(at.get('download_button'))
    def test_create_and_near_duplicate_requires_confirmation(self):
        at=self.app
        widget(at.text_input,'Nom du nouveau produit').set_value('Café noire').run()
        self.assertTrue(widget(at.button,'Ajouter le produit').disabled)
        widget(at.checkbox,'J’ai vérifié : il s’agit d’un produit différent').check().run()
        widget(at.button,'Ajouter le produit').click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(db.products()),2)
    def test_seller_sees_no_admin_controls(self):
        self.app.session_state['user']={'id':2,'role':'seller'}
        self.app.run()
        self.assertFalse(self.app.exception)
        self.assertEqual(len(self.app.button),0)
        self.assertEqual(len(self.app.text_input),0)

    def test_real_mobile_and_desktop_product_sections(self):
        for filename,start_marker,end_marker in [
            ('iphone_app.py','elif page == "Produits":','elif page == "Achats":'),
            ('app.py','elif page == "Produits et stock":','elif page == "Clients et fournisseurs":')]:
            code=Path(__file__).with_name(filename).read_text(encoding='utf-8')
            section=code[code.index(start_marker):code.index(end_marker)]
            section=section.replace(start_marker,'if True:',1)
            source="import streamlit as st\nimport db\nimport v3_ui\nuser={'id':1,'role':'admin'}\nis_admin=True\n"+section
            with self.subTest(filename=filename):
                app=AppTest.from_string(source,default_timeout=20).run()
                self.assertFalse(app.exception)
                self.assertIsNotNone(widget(app.button,'Archiver le produit'))
                self.assertIsNotNone(widget(app.button,'Enregistrer le stock'))


if __name__=='__main__': unittest.main()

