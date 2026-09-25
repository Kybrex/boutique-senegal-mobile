"""Cloud adapter tests: no network and no production credentials."""
from unittest.mock import patch
from types import SimpleNamespace
import workflow_service as service
import cloud_db as cloud

def run():
    objects={}
    uploads=[]
    class Bucket:
        def upload(self,key,data,options):
            uploads.append(options)
            if key in objects:
                raise RuntimeError('already exists')
            objects[key]=data
        def download(self,key):
            return objects[key]
    class Storage:
        def get_bucket(self,name):
            assert name=='automatic-backups'
            return SimpleNamespace(public=False)
        def from_(self,name):
            return Bucket()
    client=SimpleNamespace(storage=Storage())
    key='documents-v1/invoices/VENTE/1.json'
    with patch.object(service.cloud,'enabled',return_value=True),patch.object(service.cloud,'client',return_value=client):
        assert service.write_object_once(key,b'original')==b'original'
        assert service.write_object_once(key,b'replacement')==b'original'
        assert objects[key]==b'original'
        assert all(x['upsert']=='false' for x in uploads)
        assert service.read_object(key)==b'original'
    # Broken writes must fail visibly and must not be indexed as successful.
    class BrokenBucket(Bucket):
        def upload(self,*args): raise RuntimeError('offline')
        def download(self,*args): raise RuntimeError('offline')
    with patch.object(service.cloud,'enabled',return_value=True),patch.object(service,'_bucket',return_value=BrokenBucket()):
        try:
            service.write_object_once(key,b'pdf')
        except ValueError:
            pass
        else:
            raise AssertionError('Failure hidden')
    rows=[{'id':i,'details':service.encode({'key':f'documents-v1/invoices/VENTE/{i}.json','created_at':f'2026-09-{i%28+1:02d}'}).decode()} for i in range(1,452)]
    pages=[]
    class Query:
        def select(self,*args):return self
        def eq(self,key,val):
            assert key=='action' and val==service.EVENT
            return self
        def order(self,*args,**kwargs):return self
        def range(self,a,b):
            self.a=a;self.b=b;pages.append((a,b));return self
        def execute(self):
            return SimpleNamespace(data=rows[self.a:self.b+1])
    with patch.object(service.cloud,'enabled',return_value=True),patch.object(service.cloud,'_table',return_value=Query()):
        result=service.entries({'id':1,'role':'admin'})
        assert len(result)==451
        assert pages==[(0,199),(200,399),(400,599),(451,650)]
    deleted=[]
    references={'sales':[{'id':10}], 'credit_payments':[], 'documents':[], 'products':[], 'purchase_orders':[]}
    class Related:
        def __init__(self,name): self.name=name; self.deleting=False
        def select(self,*args): return self
        def eq(self,*args): return self
        def limit(self,*args): return self
        def delete(self): self.deleting=True; return self
        def execute(self):
            if self.deleting: deleted.append(self.name); return SimpleNamespace(data=[])
            return SimpleNamespace(data=references.get(self.name,[]))
    with patch.object(cloud,'_one',return_value={'id':1}),patch.object(cloud,'_table',side_effect=Related):
        try: cloud.delete_client(1)
        except ValueError: pass
        else: raise AssertionError('Linked customer deleted')
        assert deleted==[]
        references['sales']=[]
        cloud.delete_client(1)
        assert deleted==['clients']
        references['products']=[{'id':3}]
        try: cloud.delete_supplier(1)
        except ValueError: pass
        else: raise AssertionError('Linked supplier deleted')
        assert deleted==['clients']
    print('PASS: private cloud storage, create-only collision handling, failures surfaced, complete archive pagination')

if __name__=='__main__':
    run()
