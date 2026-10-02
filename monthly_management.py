"""Monthly goals and product analysis for both database backends."""
from datetime import date, timedelta
import math
import pandas as pd
import db
import business_features as features
import product_lifecycle as lifecycle
import workflow_service as workflows

def month_bounds(day):
    start = day.replace(day=1)
    next_month = date(start.year+1,1,1) if start.month==12 else date(start.year,start.month+1,1)
    return start, next_month-timedelta(days=1)

def goal(day):
    return float(features.read_setting(f'objectif_vente_{day:%Y-%m}', {'amount':0}).get('amount',0))

def save_goal(day, amount, user):
    features.require_admin(user)
    amount=float(amount)
    if not math.isfinite(amount) or amount<0: raise ValueError('L’objectif doit être un montant positif ou zéro.')
    features.write_setting(f'objectif_vente_{day:%Y-%m}', {'amount':amount}, user)

def goal_progress(revenue, amount):
    return {'ratio':min(max(revenue/amount,0),1) if amount>0 else 0,
            'percent':revenue/amount*100 if amount>0 else 0, 'remaining':max(amount-revenue,0)}

def product_analysis(start, end):
    products=features.records('products')
    sales={r['id']:r for r in features.records('sales') if start.isoformat()<=str(r['created_at'])[:10]<=end.isoformat()}
    items=[r for r in features.records('sale_items') if r['sale_id'] in sales]
    gross={}
    for r in items: gross[r['sale_id']]=gross.get(r['sale_id'],0)+int(r['quantity'])*float(r['unit_price'])
    totals={}
    for r in items:
        sid=r['sale_id']; qty=int(r['quantity']); value=qty*float(r['unit_price'])
        item=totals.setdefault(r['product_id'], {'Quantité':0,'Ventes':0.0})
        item['Quantité']+=qty
        item['Ventes']+=value*(float(sales[sid]['total'])/gross[sid]) if gross[sid] else 0
    archived=lifecycle.archived_ids()
    stocks={}
    for row in features.records('store_stock'):
        stocks[row['product_id']]=stocks.get(row['product_id'],0)+int(row['stock'])
    rows=[]
    for p in products:
        values=totals.get(p['id'], {'Quantité':0,'Ventes':0.0})
        rows.append({'N°':p['id'],'Produit':p['name'],'Catégorie':p.get('category') or '',
                     'Stock':stocks.get(p['id'],int(p['stock'])), 'Archivé':p['id'] in archived, **values})
    frame=pd.DataFrame(rows,columns=['N°','Produit','Catégorie','Stock','Archivé','Quantité','Ventes'])
    top=frame.loc[frame.Quantité.gt(0)].sort_values(['Quantité','Ventes'],ascending=False)
    unsold=frame.loc[frame.Quantité.eq(0)&frame.Stock.gt(0)&~frame.Archivé]
    return top,unsold

def monthly_snapshot(day):
    start,end=month_bounds(day)
    profit=features.profit_summary(start,end)
    top,unsold=product_analysis(start,end)
    debts=features.debt_rows('clients')
    return {'start':start,'end':end,'profit':profit,'goal':goal(start),'top':top,'unsold':unsold,
            'debts':debts, 'debt_total':float(debts.Reste.sum()) if not debts.empty else 0,
            'as_of':date.today()}

def client_reminder(identifier,user):
    profile=workflows.client_profile(identifier,user)
    client=profile['client']
    if not client: raise ValueError('Client introuvable.')
    debts=[r for r in profile['sales'] if float(r['total'])-float(r['paid'])>.005]
    if not debts: raise ValueError('Ce client n’a aucun impayé.')
    amount=sum(float(r['total'])-float(r['paid']) for r in debts)
    shop=db.get_settings().get('shop_name') or 'Boutique Sénégal'
    message=f"Bonjour {client['name']}, voici votre situation chez {shop} : {len(debts)} vente(s) avec un solde total de {amount:,.0f} FCFA. Merci de nous contacter pour convenir du règlement."
    return client.get('phone') or '',message
