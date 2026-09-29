"""Deletion tests use temporary SQLite only; cloud requests are simulated."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import gc

import db
import product_management as pm

ADMIN = {'id': 1, 'role': 'admin'}


class LocalDeletionTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.folder.name) / 'test.db'
        self.cloud = patch.object(pm.cloud, 'enabled', return_value=False)
        self.cloud.start()
        db.init_db()
        db.add_product('Produit test', '', 100, 200, 5, 1, None)
        self.pid = int(db.products().iloc[0].id)

    def tearDown(self):
        db.DB_PATH = self.old_path
        self.cloud.stop()
        gc.collect()
        self.folder.cleanup()

    def delete(self, **kwargs):
        args = dict(user=ADMIN, product_id=self.pid, expected_stock=5, reason='Doublon')
        args.update(kwargs)
        return pm.delete_product(**args)

    def test_delete_and_audit(self):
        db.execute('INSERT OR REPLACE INTO store_stock VALUES(1,?,5)', (self.pid,))
        self.delete()
        self.assertTrue(db.products().empty)
        self.assertTrue(db.query('SELECT * FROM store_stock').empty)
        log = db.query("SELECT * FROM activity_logs WHERE action='PRODUIT_SUPPRIME'").iloc[0]
        self.assertIn('stock supprimé : 5', log.details)
        self.assertIn('Doublon', log.details)

    def test_role_reason_missing_and_stale(self):
        for args in ({'user':None}, {'user':{'id':2,'role':'seller'}}, {'reason':' '},
                     {'reason':'x'*201}, {'product_id':999}, {'expected_stock':4}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.delete(**args)
        self.assertEqual(int(db.products().iloc[0].Stock), 5)

    def test_deleted_reference_is_not_reused(self):
        self.delete()
        db.add_product('Nouveau', '', 100, 200, 2, 0, None)
        self.assertGreater(int(db.products().iloc[0].id), self.pid)

    def test_history_and_variants_are_preserved(self):
        inserts = {
            'sale_items': 'INSERT INTO sale_items(sale_id,product_id,quantity,unit_price) VALUES(1,?,1,200)',
            'document_items': 'INSERT INTO document_items(document_id,product_id,quantity,unit_price) VALUES(1,?,1,200)',
            'purchase_order_items': 'INSERT INTO purchase_order_items(purchase_order_id,product_id,quantity,unit_cost) VALUES(1,?,1,100)',
            'returns': "INSERT INTO returns(sale_id,product_id,quantity,resolution) VALUES(1,?,1,'REMBOURSEMENT')",
            'inventory_counts': 'INSERT INTO inventory_counts(product_id,expected_stock,counted_stock,difference) VALUES(?,5,5,0)',
            'stock_transfers': 'INSERT INTO stock_transfers(product_id,from_store_id,to_store_id,quantity) VALUES(?,1,2,1)',
            'product_lots': "INSERT INTO product_lots(product_id,batch_number,expiry_date) VALUES(?,'A','2030-01-01')",
            'product_variants': "INSERT INTO product_variants(product_id,name) VALUES(?,'Bleu')",
        }
        for table, sql in inserts.items():
            with self.subTest(table=table):
                db.execute(sql, (self.pid,))
                with self.assertRaisesRegex(ValueError, 'lié'):
                    self.delete()
                self.assertEqual(len(db.products()), 1)
                self.assertEqual(len(db.query(f'SELECT * FROM {table}')), 1)
                db.execute(f'DELETE FROM {table}')

    def test_other_store_stock(self):
        db.execute('INSERT INTO store_stock VALUES(2,?,3)', (self.pid,))
        with self.assertRaisesRegex(ValueError, 'autre boutique'):
            self.delete()
        self.assertEqual(int(db.query('SELECT stock FROM store_stock WHERE store_id=2').iloc[0].stock), 3)

    def test_audit_failure_rolls_back(self):
        db.execute("CREATE TRIGGER reject_log BEFORE INSERT ON activity_logs BEGIN SELECT RAISE(ABORT, 'test'); END")
        with self.assertRaises(Exception):
            self.delete()
        self.assertEqual(len(db.products()), 1)


class FakeTable:
    def __init__(self, backend, name):
        self.backend, self.name, self.filters, self.deleting = backend, name, {}, False
    def select(self, *args): return self
    def eq(self, key, value): self.filters[key] = value; return self
    def limit(self, *args): return self
    def delete(self): self.deleting = True; return self
    def execute(self):
        rows = [r for r in self.backend.rows.get(self.name, []) if all(r.get(k) == v for k,v in self.filters.items())]
        if self.deleting:
            if self.backend.conflict:
                error = RuntimeError('FK'); error.code = '23503'; raise error
            if self.backend.stale: return SimpleNamespace(data=[])
            self.backend.deleted.append(self.name)
            self.backend.rows[self.name] = [r for r in self.backend.rows[self.name] if r not in rows]
        return SimpleNamespace(data=rows)


class CloudDeletionTests(unittest.TestCase):
    def setUp(self):
        self.rows = {'products':[{'id':1,'name':'Test','stock':5}], 'stores':[{'id':1,'name':'Boutique principale'}]}
        self.deleted, self.conflict, self.stale = [], False, False
        self.patches = [patch.object(pm.cloud,'enabled',return_value=True),
                        patch.object(pm.cloud,'_table',side_effect=lambda name:FakeTable(self,name)),
                        patch.object(db,'log_action')]
        self.mocks = [p.start() for p in self.patches]
    def tearDown(self):
        for p in reversed(self.patches): p.stop()
    def delete(self): return pm.delete_product(ADMIN,1,5,'Doublon')
    def test_success_single_parent_delete(self):
        self.delete()
        self.assertEqual(self.deleted,['products'])
        self.mocks[-1].assert_called_once()
    def test_each_dependency_blocks(self):
        for table,_ in pm.LINKED_TABLES:
            self.rows[table] = [{'id':1,'product_id':1}]
            with self.assertRaises(ValueError): self.delete()
            del self.rows[table]
        self.assertEqual(self.deleted,[])
    def test_concurrent_history_and_stock(self):
        self.conflict = True
        with self.assertRaisesRegex(ValueError,'historique'): self.delete()
        self.conflict, self.stale = False, True
        with self.assertRaisesRegex(ValueError,'changé'): self.delete()
        self.mocks[-1].assert_not_called()
    def test_other_store(self):
        self.rows['store_stock'] = [{'product_id':1,'store_id':2,'stock':2}]
        with self.assertRaisesRegex(ValueError,'autre boutique'): self.delete()
        self.assertEqual(self.deleted,[])
    def test_read_failure_is_not_ignored(self):
        with patch.object(pm.cloud,'_table',side_effect=RuntimeError('network')):
            with self.assertRaises(RuntimeError): self.delete()
        self.assertEqual(self.deleted,[])
    def test_audit_warning_after_success(self):
        self.mocks[-1].side_effect = RuntimeError('audit unavailable')
        with self.assertLogs(pm.__name__,level='ERROR'):
            self.assertIn('journal',self.delete())
        self.assertEqual(self.deleted,['products'])


if __name__ == '__main__':
    unittest.main()
