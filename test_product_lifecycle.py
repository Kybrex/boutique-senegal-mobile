from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from datetime import date
import gc
import unittest
import db
import cloud_db
import product_lifecycle as life
from product_history import history
from product_management import delete_product
import v3_db
import v4_db

ADMIN = {'id':1,'role':'admin'}
SELLER = {'id':2,'role':'seller'}


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.folder.name)/'test.db'
        self.mock = patch.object(cloud_db,'enabled',return_value=False)
        self.mock.start()
        db.init_db()
        db.add_product('Café noir','Boissons',100,200,10,12,None)
        self.pid = int(db.products().iloc[0].id)
        db.update_product_details(self.pid,'123','')

    def tearDown(self):
        db.DB_PATH = self.old_path
        self.mock.stop()
        gc.collect()
        self.folder.cleanup()

    def cart(self): return [{'id':self.pid,'quantity':2,'sale_price':200}]
    def archive(self): life.set_archived(ADMIN,self.pid,True,'Fin de gamme')

    def test_archive_restore_preserves_stock_and_sale(self):
        sale_id = db.save_sale(self.cart(),1,None,400,'Especes',0)[0]
        self.archive()
        self.assertTrue(db.products().empty)
        self.assertTrue(db.inventory_snapshot().empty)
        self.assertTrue(db.store_inventory(1).empty)
        self.assertTrue(db.low_stock().empty)
        self.assertIsNone(db.find_product_by_barcode('123'))
        self.assertEqual(int(db.products(include_archived=True).iloc[0].Stock),8)
        self.assertEqual(int(db.sale_details(sale_id)[1].iloc[0].Quantite),2)
        self.assertEqual(len(db.report(date.today(),date.today())),1)
        life.set_archived(ADMIN,self.pid,False,'Retour en boutique')
        self.assertEqual(int(db.products().iloc[0].Stock),8)
        self.assertEqual(int(db.find_product_by_barcode('123')['id']),self.pid)
        self.assertEqual(list(history(self.pid)['Événement']).count('Archivage'),1)
        self.assertEqual(list(history(self.pid)['Événement']).count('Restauration'),1)

    def test_old_cart_and_documents_blocked(self):
        self.archive()
        for action in [lambda:db.save_sale(self.cart(),1,None,400,'Especes',0),
                       lambda:v4_db.atomic_save_sale(self.cart(),1,None,400,'Especes',0),
                       lambda:v3_db.create_document('DEVIS',None,None,'',[{'product_id':self.pid,'quantity':1,'unit_price':200}],1),
                       lambda:v3_db.create_purchase_order(1,None,'',[{'product_id':self.pid,'quantity':1,'unit_cost':100}],1)]:
            with self.assertRaisesRegex(ValueError,'archivé'): action()
        self.assertTrue(db.query('SELECT * FROM sales').empty)

    def test_duplicate_normalization_and_archived(self):
        for name in [' CAFE   NOIR ','café-noir','Café noir']:
            with self.assertRaisesRegex(ValueError,'existe déjà'):
                db.add_product(name,'',1,2,0,0,None)
        self.archive()
        with self.assertRaisesRegex(ValueError,'archivés'):
            db.add_product('cafe noir','',1,2,0,0,None)
        self.assertTrue(life.duplicate_candidates('Café noire'))
        db.add_product('Café rouge','',1,2,0,0,None)
        self.assertEqual(len(db.products(include_archived=True)),2)

    def test_identity_and_stale_edit(self):
        life.update_identity(ADMIN,self.pid,'Café premium','Épicerie','Café noir','Boissons')
        self.assertEqual(db.products().iloc[0].Produit,'Café premium')
        self.assertEqual(int(db.products().iloc[0].id),self.pid)
        frame = history(self.pid)
        self.assertIn('Café noir',frame.loc[frame['Événement']=='Fiche modifiée','Détail'].iloc[0])
        with self.assertRaisesRegex(ValueError,'changé'):
            life.update_identity(ADMIN,self.pid,'Ancienne saisie','','Café noir','Boissons')
        db.add_product('Autre','',1,2,0,0,None)
        with self.assertRaisesRegex(ValueError,'existe déjà'):
            life.update_identity(ADMIN,self.pid,'AUTRE','','Café premium','Épicerie')

    def test_admin_required(self):
        for user in [None,SELLER]:
            for action in [lambda:life.set_archived(user,self.pid,True,'test'),
                           lambda:life.update_identity(user,self.pid,'X','','Café noir','Boissons'),
                           lambda:life.change_stock(user,self.pid,'Retirer',1,10,'Casse')]:
                with self.assertRaises(ValueError): action()
        self.assertEqual(life.archived_ids(),set())
        self.assertEqual(int(db.products().iloc[0].Stock),10)

    def test_all_exit_reasons_and_history(self):
        for index,reason in enumerate(life.EXIT_REASONS):
            life.change_stock(ADMIN,self.pid,'Retirer',1,10-index,reason,'Échantillon' if reason=='Autre' else '')
        frame=history(self.pid)
        exits=frame[frame['Événement']=='Sortie']
        self.assertEqual(len(exits),6)
        self.assertEqual(int(exits['Quantité'].sum()),-6)
        self.assertEqual(int(db.store_inventory(1).iloc[0].Stock),4)
        with self.assertRaisesRegex(ValueError,'Archivez'):
            delete_product(ADMIN,self.pid,4,'Test')

    def test_invalid_and_stale_stock(self):
        cases=[('Retirer',11,10,'Casse',''),('Retirer',1,9,'Casse',''),('Définir',5,10,'',''),
               ('Retirer',1,10,'Autre',''),('Ajouter',0,10,'',''),('Retirer',1.5,10,'Casse','')]
        for mode,amount,expected,reason,note in cases:
            with self.subTest(case=mode),self.assertRaises(ValueError):
                life.change_stock(ADMIN,self.pid,mode,amount,expected,reason,note)
        self.assertEqual(int(db.products().iloc[0].Stock),10)
        self.archive()
        with self.assertRaises(ValueError):
            life.change_stock(ADMIN,self.pid,'Ajouter',1,10,'')

    def test_movement_rollback_when_journal_fails(self):
        db.execute("CREATE TRIGGER reject_product_event BEFORE INSERT ON activity_logs BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(Exception):
            life.change_stock(ADMIN,self.pid,'Retirer',2,10,'Perte')
        self.assertEqual(int(db.products().iloc[0].Stock),10)

    def test_returns_reconstruct_original_sale(self):
        sale_id=db.save_sale(self.cart(),1,None,400,'Especes',0)[0]
        v3_db.process_return(sale_id,self.pid,2,'Défaut','REMBOURSEMENT','Especes',1)
        self.archive()
        frame=history(self.pid)
        self.assertEqual(int(frame.loc[frame['Événement']=='Vente','Quantité'].sum()),-2)
        self.assertEqual(int(frame.loc[frame['Événement']=='Retour','Quantité'].sum()),2)

    def test_purchase_and_receipt_history(self):
        db.register_purchase(self.pid,3,100,'Fournisseur')
        oid=v3_db.create_purchase_order(1,None,'',[{'product_id':self.pid,'quantity':5,'unit_cost':100}],1)
        item=int(v3_db.purchase_order_details(oid).iloc[0].id)
        v3_db.receive_purchase_order_item(oid,item,2)
        frame=history(self.pid)
        self.assertEqual(int(frame.loc[frame['Événement']=='Achat reçu','Quantité'].sum()),3)
        self.assertEqual(int(frame.loc[frame['Événement']=='Réception fournisseur','Quantité'].sum()),2)
        self.assertFalse((frame['Événement']=='Anciennes réceptions').any())

    def test_import_respects_archive_and_normalization(self):
        self.archive()
        result=v4_db.import_rows('products',[{'nom':'CAFE NOIR','vente':200,'stock':9},{'nom':'Café noir','vente':200,'stock':9}])
        self.assertEqual(result['ignored'],2)
        self.assertEqual(int(db.products(include_archived=True).iloc[0].Stock),10)

    def test_corrupt_archive_state_fails_closed(self):
        db.execute('INSERT INTO activity_logs(action,details) VALUES(?,?)',(life.ARCHIVE_PREFIX+str(self.pid),'broken'))
        with self.assertRaisesRegex(ValueError,'illisible'): db.products()


if __name__ == '__main__': unittest.main()

