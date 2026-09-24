"""Daily cash journal. Uses existing tables and persistent configuration events."""
from datetime import date
import math
import json
import pandas as pd
import db
import business_features as f

METHODS = ['Especes', 'Wave', 'Orange Money', 'Carte']
COLUMNS = ['Date', 'Origine', 'Référence', 'Paiement', 'Entrée', 'Sortie']

def method(value):
    key = f.normalized(value or '').strip()
    return {'especes':'Especes', 'wave':'Wave', 'orange money':'Orange Money', 'carte':'Carte',
            'hors caisse':'Hors caisse', 'avoir':'Avoir'}.get(key, 'À préciser')

def journal(start, end):
    if start > end:
        raise ValueError('La date de début doit précéder la date de fin.')
    sales = f.records('sales')
    payments = f.records('credit_payments')
    returns = f.records('returns')
    expense_methods = {}
    events = f.records('activity_logs')
    for event in sorted(events, key=lambda r:r['id']):
        if str(event.get('action','')).startswith('BOUTIQUE_CONFIG:expense_method:'):
            expense_methods[int(event['action'].rsplit(':',1)[1])] = json.loads(event['details'])['method']
    rows = []
    def add(when, origin, reference, mode, incoming=0, outgoing=0):
        day = str(when)[:10]
        if start.isoformat() <= day <= end.isoformat() and (incoming or outgoing):
            rows.append(dict(zip(COLUMNS,[day,origin,reference,method(mode),round(incoming,2),round(outgoing,2)])))
    for s in sales:
        later = sum(float(p['amount']) for p in payments if p.get('sale_id') == s['id'])
        reversed_paid = sum(float(r['refund_amount']) for r in returns if r['sale_id'] == s['id'])
        initial = max(0, float(s['paid']) + reversed_paid - later)
        # Older records can contain the tendered cash including change.
        initial = min(initial, max(0,float(s['total']) + reversed_paid))
        add(s['created_at'],'Vente',f"Vente #{s['id']}",s['payment_method'],initial)
    for p in payments:
        add(p['created_at'],'Règlement client',f"Vente #{p.get('sale_id')}",p['payment_method'],float(p['amount']))
    for r in returns:
        if r['resolution'] in ('REMBOURSEMENT','ECHANGE'):
            add(r['created_at'],'Remboursement',f"Retour #{r['id']} · vente #{r['sale_id']}",r['refund_method'],outgoing=float(r['refund_amount']))
    for p in f.records('supplier_payments'):
        add(p['created_at'],'Règlement fournisseur',f"Commande #{p['purchase_order_id']}",p['payment_method'],outgoing=float(p['amount']))
    for e in f.records('expenses'):
        if str(e['label']).startswith('Règlement fournisseur - commande #'):
            continue  # Already represented by supplier_payments.
        add(e['created_at'],'Dépense',f"Dépense #{e['id']} · {e['label']}",expense_methods.get(e['id']),outgoing=float(e['amount']))
    for event in events:
        if event.get('action')=='BOUTIQUE_CASH_OPEN':
            opening=json.loads(event['details'])
            add(opening['date'],'Mouvement de caisse','Ouverture de caisse','Especes',float(opening['amount']))
    for m in f.records('cash_movements'):
        # Legacy return movements duplicate the returns table.
        if str(m['label']).startswith('Remboursement ticket #'):
            continue
        value = float(m['amount'])
        add(m['movement_date'],'Mouvement de caisse',m['label'],'Especes',
            value if m['movement_type'] in ('ENTREE','FOND_INITIAL') else 0,
            value if m['movement_type']=='SORTIE' else 0)
    return pd.DataFrame(rows, columns=COLUMNS).sort_values('Date',kind='stable')

def totals(rows):
    summary = rows.groupby('Paiement')[['Entrée','Sortie']].sum().reindex(METHODS + ['Avoir','Hors caisse','À préciser'],fill_value=0)
    summary['Net'] = summary['Entrée']-summary['Sortie']
    return summary.reset_index()

def classify_expense(identifier, mode, user):
    f.require_admin(user)
    if mode not in METHODS + ['Hors caisse']:
        raise ValueError('Mode de paiement invalide.')
    if not any(e['id']==identifier for e in f.records('expenses')):
        raise ValueError('Dépense introuvable.')
    f.write_setting('expense_method:'+str(identifier),{'method':mode},user)

def opened(day):
    legacy=[r for r in f.records('cash_movements') if r['movement_date']==day.isoformat() and r['movement_type']=='FOND_INITIAL']
    for event in f.records('activity_logs'):
        if event.get('action')=='BOUTIQUE_CASH_OPEN':
            value=json.loads(event['details'])
            if value['date']==day.isoformat():
                legacy.append(value)
    return legacy

def closed(day):
    return [r for r in f.records('cash_closings') if str(r['closing_date'])[:10]==day.isoformat() and r.get('seller_id') is None]

def open_day(day, amount, user):
    f.require_admin(user)
    if day != date.today():
        raise ValueError('Ouvrez la caisse pour la journée actuelle.')
    if not math.isfinite(amount) or amount<0:
        raise ValueError('Fonds initial invalide.')
    if opened(day) or closed(day):
        raise ValueError('Cette journée est déjà ouverte ou clôturée.')
    import cloud_db as cloud
    # Reserve the UTC-midnight millisecond ID; ordinary rows use other IDs.
    payload={'id':(day-date(1970,1,1)).days*86400000,'action':'BOUTIQUE_CASH_OPEN',
             'details':json.dumps({'date':day.isoformat(),'amount':amount}), 'user_id':int(user['id'])}
    if cloud.enabled():
        cloud._table('activity_logs').insert(payload).execute()
    else:
        db.execute('INSERT INTO activity_logs(id,action,details,user_id) VALUES(?,?,?,?)',tuple(payload.values()))

def close_day(day, counted, notes, user):
    f.require_admin(user)
    if not math.isfinite(counted) or counted < 0:
        raise ValueError('Montant compté invalide.')
    if not opened(day) or closed(day):
        raise ValueError('Ouvrez la caisse avant la clôture ; une journée clôturée ne peut pas être clôturée à nouveau.')
    rows=journal(day,day)
    if (rows.Paiement=='À préciser').any():
        raise ValueError('Précisez les modes de paiement avant la clôture.')
    expected=float(totals(rows).set_index('Paiement').loc['Especes','Net'])
    if abs(counted-expected)>.005 and not notes.strip():
        raise ValueError('Expliquez l’écart entre le montant attendu et le montant compté.')
    import cloud_db as cloud
    # Reserve the UTC-midnight millisecond ID; ordinary rows use other IDs.
    payload={'id':(day-date(1970,1,1)).days*86400000, 'closing_date':day.isoformat(), 'seller_id':None,
             'expected_cash':expected,'counted_cash':counted,'difference':counted-expected,
             'notes':notes.strip(),'closed_by':int(user['id'])}
    if cloud.enabled():
        cloud._table('cash_closings').insert(payload).execute()
    else:
        db.execute('INSERT INTO cash_closings(id,closing_date,seller_id,expected_cash,counted_cash,difference,notes,closed_by) VALUES(?,?,?,?,?,?,?,?)',tuple(payload.values()))
    return expected

def reminder(sale_id, user):
    f.require_admin(user)
    sale=next((r for r in f.records('sales') if r['id']==sale_id),None)
    if not sale or not sale.get('due_date') or str(sale['due_date'])[:10]>date.today().isoformat():
        raise ValueError('Cette vente n’est pas arrivée à échéance.')
    balance=max(0,float(sale['total'])-float(sale['paid']))
    if balance<=.005:
        raise ValueError('Cette vente est déjà réglée.')
    client=next((r for r in f.records('clients') if r['id']==sale.get('client_id')),None)
    if not client:
        raise ValueError('Associez un client à cette vente.')
    text=f"Bonjour {client['name']}, rappel de Boutique Sénégal : le solde de la facture {f.invoice_number(sale_id)} est de {balance:,.0f} FCFA, échéance du {str(sale['due_date'])[:10]}. Merci de nous contacter pour le règlement."
    return client.get('phone') or '', text
