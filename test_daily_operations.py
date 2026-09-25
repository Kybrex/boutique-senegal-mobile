"""Isolated checks for daily operations; never touches production."""
from datetime import date,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace
import gc
import db, v3_db as v3, business_features as f, daily_operations as ops
import cloud_db as cloud

def rejects(action):
    try: action()
    except ValueError: return
    raise AssertionError('Expected rejection')

def run():
    with TemporaryDirectory() as folder:
        db.DB_PATH=Path(folder)/'daily.db'
        db.init_db()
        db.create_user('admin','Admin','test-password','admin')
        user=db.authenticate('admin','test-password')
        db.create_seller_with_user('Seller','','','seller','test-password')
        db.add_client('Awa','771234567','','')
        db.add_product('Riz','Epicerie',500,1000,100,5,None)
        today=date.today()
        yesterday=today-timedelta(days=1)
        cart=[{'id':1,'quantity':2,'sale_price':1000}]
        one=db.save_sale(cart,1,1,1800,'Especes',200)[0]
        two=db.save_sale(cart,1,1,500,'Especes',0,today)[0]
        db.execute('UPDATE sales SET created_at=? WHERE id IN (?,?)',(yesterday.isoformat(),one,two))
        db.add_credit_payment(1,two,300,'Especes',int(user['id']))
        stock=int(db.products().iloc[0].Stock)
        refund=v3.process_return(one,1,1,'Article abîmé','REMBOURSEMENT','Especes',int(user['id']))
        assert refund==900
        sale,_=db.sale_details(one)
        assert sale['total']==900 and sale['discount']==100 and sale['paid']==900
        assert int(db.products().iloc[0].Stock)==stock+1
        assert v3.process_return(two,1,1,'Retour partiel','REMBOURSEMENT','Wave',int(user['id']))==0
        sale,_=db.sale_details(two)
        assert sale['total']==1000 and sale['paid']==800
        three=db.save_sale(cart,1,1,2000,'Wave',0)[0]
        assert v3.process_return(three,1,1,'Retour','ECHANGE','Wave',int(user['id']))==1000
        rejects(lambda:v3.process_return(three,1,9,'Retour','REMBOURSEMENT','Wave',int(user['id'])))
        rejects(lambda:v3.process_return(three,1,1,'','REMBOURSEMENT','Wave',int(user['id'])))
        four=db.save_sale(cart,1,None,2000,'Especes',0)[0]
        rejects(lambda:v3.process_return(four,1,1,'Retour','AVOIR','Especes',int(user['id'])))
        db.execute('UPDATE sales SET created_at=? WHERE id=?',(yesterday.isoformat(),four))
        five=db.save_sale(cart,1,1,2000,'Carte',0)[0]
        assert v3.process_return(five,1,1,'Retour','AVOIR','Carte',int(user['id']))==1000
        assert float(db.clients().iloc[0].Avoir)==1000
        assert f.profit_summary(today,today)['revenue']==2000
        j=ops.journal(today,today)
        totals=ops.totals(j).set_index('Paiement')
        assert totals.loc['Especes','Net']==-600 # 300 settlement less 900 refund
        assert totals.loc['Wave','Entrée']==2000 and totals.loc['Wave','Sortie']==1000
        assert totals.loc['Carte','Entrée']==2000 and totals.loc['Carte','Sortie']==0
        yesterday_totals=ops.totals(ops.journal(yesterday,yesterday)).set_index('Paiement')
        assert yesterday_totals.loc['Especes','Entrée']==4300 # 1800 + 500 + 2000, not later settlement
        assert not f.records('cash_movements')
        db.add_expense('Transport',500)
        ops.open_day(today,10000,user)
        rejects(lambda:ops.open_day(today,0,user))
        rejects(lambda:ops.close_day(today,8900,'',user)) # Unknown expense mode
        ops.classify_expense(1,'Especes',user)
        rejects(lambda:ops.close_day(today,8000,'',user))
        assert ops.close_day(today,8900,'',user)==8900
        rejects(lambda:ops.close_day(today,8900,'',user))
        assert ops.closed(today)[0]['difference']==0
        rejects(lambda:ops.open_day(today,0,{'role':'seller'}))
        rejects(lambda:ops.classify_expense(1,'Wave',{'role':'seller'}))
        phone,message=ops.reminder(two,user)
        assert phone=='771234567' and '200 FCFA' in message
        rejects(lambda:ops.reminder(one,user))
        rejects(lambda:ops.reminder(two,{'role':'seller'}))
        # Supplier payment expense must not be counted twice.
        db.add_supplier('Supplier','','','','')
        po=v3.create_purchase_order(1,today,'',[{'product_id':1,'quantity':1,'unit_cost':500}],int(user['id']))
        v3.add_supplier_payment(po,500,'Wave',int(user['id']))
        after=ops.totals(ops.journal(today,today)).set_index('Paiement')
        assert after.loc['Wave','Sortie']==1500
        # Cloud return computes exactly the same retained discount and paid amount.
        import pandas as pd
        calls=[]
        class Table:
            def update(self, values): calls.append(values); return self
            def delete(self): return self
            def eq(self,*args): return self
            def execute(self): return SimpleNamespace(data=[])
        old={'id':90,'total':1800,'discount':200,'paid':1800,'commission_amount':180}
        before=(old,pd.DataFrame([{'Total':2000}]))
        after=(old,pd.DataFrame([{'Total':1000}]))
        with patch.object(cloud,'sale_details',side_effect=[before,after]), patch.object(cloud,'_one',return_value={'id':1,'quantity':2}),patch.object(cloud,'_table',return_value=Table()),patch.object(cloud,'adjust_stock'):
            assert cloud.return_sale_item(90,1,1)==900
        assert calls[-1]=={'total':900,'discount':100,'paid':900,'commission_amount':90}
        gc.collect()
    print('PASS: cash dates, payment modes, partial debt, returns, exchanges, credit notes, opening/closing, reminders and cloud return arithmetic')

if __name__=='__main__': run()
