"""Catalogue round trips beyond the audit log's former 500-character limit."""
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
from catalog_library import list_catalogs, save_catalog, CatalogDataError


def run():
    for remote in (False, True):
        conn = sqlite3.connect(':memory:')
        conn.execute('CREATE TABLE activity_logs(id INTEGER PRIMARY KEY,user_id INTEGER,action TEXT,details TEXT)')
        def query(sql, params=()): return pd.read_sql_query(sql, conn, params=params)
        def execute(sql, params): conn.execute(sql, params); conn.commit()
        class Table:
            def select(self, cols): return self
            def eq(self, key, value): self.action=value; return self
            def order(self, *a, **kw): return self
            def limit(self, n): self.n=n; return self
            def insert(self, row): self.row=row; return self
            def execute(self):
                if hasattr(self, 'row'):
                    execute('INSERT INTO activity_logs(user_id,action,details) VALUES(?,?,?)', tuple(self.row[k] for k in ('user_id','action','details')))
                    return SimpleNamespace(data=[])
                return SimpleNamespace(data=query('SELECT details FROM activity_logs WHERE action=? ORDER BY id DESC LIMIT ?', (self.action,self.n)).to_dict('records'))
        def read_setting(key, default):
            rows=query('SELECT details FROM activity_logs WHERE action=? ORDER BY id DESC LIMIT 1', ('BOUTIQUE_CONFIG:'+key,))
            return json.loads(rows.iloc[0].details) if not rows.empty else default
        def require_admin(user):
            if user['role'] != 'admin': raise ValueError('Admin required')
        features=SimpleNamespace(require_admin=require_admin, read_setting=read_setting,
            db=SimpleNamespace(query=query,execute=execute),
            cloud=SimpleNamespace(enabled=lambda:remote,_table=lambda name:Table()))
        user={'id':1,'role':'admin'}
        preset={'product_ids':[1], 'options':{'details':{'1':{'Description':'Étoffe & couleurs. '*100}}}}
        with patch.dict('sys.modules', {'business_features':features}):
            save_catalog(user,'Collection',preset)
            assert list_catalogs(user)['Collection']['options'] == preset['options']
            payload=conn.execute('SELECT details FROM activity_logs ORDER BY id DESC LIMIT 1').fetchone()[0]
            assert len(payload)>500
            execute('INSERT INTO activity_logs(user_id,action,details) VALUES(?,?,?)',(1,'BOUTIQUE_CONFIG:catalogues:1',payload[:500]))
            try: list_catalogs(user)
            except CatalogDataError as exc: assert 'Collection' in exc.recovered
            else: raise AssertionError('Corruption not reported')
            save_catalog(user,'Nouveau',preset)
            assert set(list_catalogs(user)) == {'Collection','Nouveau'}
            conn.execute('DELETE FROM activity_logs')
            execute('INSERT INTO activity_logs(user_id,action,details) VALUES(?,?,?)',(1,'BOUTIQUE_CONFIG:catalogues:1',payload[:500]))
            try: list_catalogs(user)
            except CatalogDataError as exc: assert exc.recovered == {}
            save_catalog(user,'Réparé',preset)
            assert list_catalogs(user)['Réparé']['options'] == preset['options']
        conn.close()
    print('PASS: full JSON round trip, legacy recovery, resave after corruption, SQLite and cloud adapter')


if __name__ == '__main__': run()
