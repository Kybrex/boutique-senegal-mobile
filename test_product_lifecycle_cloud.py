"""Supabase adapter contract tests with a paginated in-memory PostgREST fake."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import json
import unittest
import product_lifecycle as life
import v4_db

ADMIN={'id':1,'role':'admin'}


class Query:
    def __init__(self, backend, name):
        self.backend,self.name=backend,name
        self.tests=[]; self.span=None; self.maximum=None; self.operation=None; self.payload=None
    def select(self,*args): return self
    def order(self,*args,**kwargs): return self
    def eq(self,key,value): self.tests.append(lambda r:r.get(key)==value); return self
    def is_(self,key,value): self.tests.append(lambda r:r.get(key) is None); return self
    def in_(self,key,values): self.tests.append(lambda r:r.get(key) in values); return self
    def like(self,key,value): self.tests.append(lambda r:str(r.get(key,'')).startswith(value[:-1])); return self
    def range(self,start,end): self.span=(start,end); return self
    def limit(self,maximum): self.maximum=maximum; return self
    def update(self,payload): self.operation='update'; self.payload=payload; return self
    def insert(self,payload): self.operation='insert'; self.payload=payload; return self
    def execute(self):
        if self.backend.fail_read and self.operation is None: raise RuntimeError('network')
        table=self.backend.data.setdefault(self.name,[])
        if self.operation=='insert':
            if self.name=='activity_logs' and self.backend.fail_audit: raise RuntimeError('audit')
            record=dict(self.payload,id=max([r.get('id',0) for r in table]+[0])+1,created_at='2026-09-29T12:00:00Z')
            table.append(record); return SimpleNamespace(data=[deepcopy(record)])
        selected=[r for r in table if all(test(r) for test in self.tests)]
        if self.span:
            self.backend.pages.append((self.name,*self.span))
            selected=selected[self.span[0]:self.span[1]+1]
        if self.maximum is not None: selected=selected[:self.maximum]
        if self.operation=='update':
            if self.backend.cas_failure: return SimpleNamespace(data=[])
            for row in selected: row.update(self.payload)
        return SimpleNamespace(data=deepcopy(selected))


class CloudLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.data={'products':[{'id':1,'name':'Café noir','category':None,'stock':10}],
                   'stores':[{'id':1,'name':'Boutique principale'}],
                   'store_stock':[{'store_id':1,'product_id':1,'stock':10}], 'activity_logs':[]}
        self.fail_read=self.fail_audit=self.cas_failure=False; self.pages=[]
        self.patches=[patch.object(life.cloud,'enabled',return_value=True),patch.object(life.cloud,'_table',side_effect=lambda name:Query(self,name))]
        for p in self.patches: p.start()
    def tearDown(self):
        for p in reversed(self.patches): p.stop()
    def test_archive_restore_and_stock_preserved(self):
        life.set_archived(ADMIN,1,True,'Fin de gamme')
        self.assertEqual(life.archived_ids(),{1})
        self.assertEqual(self.data['products'][0]['stock'],10)
        life.set_archived(ADMIN,1,False,'Reprise')
        self.assertEqual(life.archived_ids(),set())
        self.assertEqual(len(self.data['activity_logs']),2)
    def test_pagination_latest_state_beyond_first_page(self):
        self.data['activity_logs']=[{'id':i,'action':life.ARCHIVE_PREFIX+str(i),'details':json.dumps({'archived':True})} for i in range(1,1201)]
        self.data['activity_logs'].append({'id':1201,'action':life.ARCHIVE_PREFIX+'1','details':json.dumps({'archived':False})})
        archived=life.archived_ids()
        self.assertNotIn(1,archived)
        self.assertIn(1200,archived)
        self.assertEqual(len(archived),1199)
    def test_duplicate_in_later_page(self):
        self.data['products']=[{'id':i,'name':f'Article {i}'} for i in range(1,600)] + [{'id':600,'name':'Café noir'}]
        with self.assertRaisesRegex(ValueError,'existe déjà'): life.validate_name('CAFE  NOIR')
    def test_cloud_product_list_has_all_pages(self):
        self.data['products']=[{'id':i,'name':f'Article {i}','stock':1,'sale_price':200,'purchase_price':100,'min_stock':0} for i in range(1,1201)]
        self.assertEqual(len(life.cloud.products()),1200)
    def test_atomic_sale_refuses_archived_before_rpc(self):
        life.set_archived(ADMIN,1,True,'Fin de gamme')
        with patch.object(life.cloud,'client') as client:
            with self.assertRaisesRegex(ValueError,'archivé'):
                v4_db.atomic_save_sale([{'id':1,'quantity':1,'sale_price':200}],1,None,200,'Especes',0)
            client.assert_not_called()
    def test_edit_null_category_and_audit(self):
        life.update_identity(ADMIN,1,'Café premium','Boissons','Café noir','')
        self.assertEqual(self.data['products'][0]['name'],'Café premium')
        self.assertEqual(json.loads(self.data['activity_logs'][0]['details'])['after']['category'],'Boissons')
    def test_stock_compare_and_set_and_reason(self):
        life.change_stock(ADMIN,1,'Retirer',3,10,'Don','Association')
        self.assertEqual(self.data['products'][0]['stock'],7)
        self.assertEqual(self.data['store_stock'][0]['stock'],7)
        event=json.loads(self.data['activity_logs'][0]['details'])
        self.assertEqual(event['delta'],-3)
        self.assertEqual(event['reason'],'Don')
    def test_stale_stock_writes_nothing(self):
        self.cas_failure=True
        with self.assertRaisesRegex(ValueError,'changé'):
            life.change_stock(ADMIN,1,'Retirer',3,10,'Don')
        self.assertEqual(self.data['products'][0]['stock'],10)
        self.assertEqual(self.data['activity_logs'],[])
    def test_read_failure_does_not_allow_sale(self):
        self.fail_read=True
        with self.assertRaises(RuntimeError): life.require_active([1])
    def test_audit_failure_does_not_repeat_stock(self):
        self.fail_audit=True
        with self.assertLogs(life.__name__,level='ERROR'):
            warning=life.change_stock(ADMIN,1,'Retirer',3,10,'Perte')
        self.assertIn('Ne répétez',warning)
        self.assertEqual(self.data['products'][0]['stock'],7)


if __name__ == '__main__': unittest.main()

