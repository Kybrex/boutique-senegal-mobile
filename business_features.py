"""Business summaries using the existing SQLite/Supabase schema."""
from datetime import date, datetime, timezone
import json
import math
import unicodedata
import pandas as pd
import db
import cloud_db as cloud


def require_admin(user):
    if user.get('role') != 'admin':
        raise ValueError('Cette action est réservée à l’administrateur.')


def records(table):
    if table not in db.BACKUP_TABLES:
        raise ValueError('Table inconnue.')
    if not cloud.enabled():
        return json.loads(db.query(f'SELECT * FROM {table}').to_json(orient='records'))
    result = []
    offset = 0
    while True:
        query = cloud._table(table).select('*')
        keys = ['store_id', 'product_id'] if table == 'store_stock' else ['id']
        for key in keys:
            query = query.order(key)
        batch = query.range(offset, offset + 499).execute().data or []
        result.extend(batch)
        if not batch:
            return result
        offset += len(batch)


def read_setting(key, default=None):
    action = 'BOUTIQUE_CONFIG:' + key
    if cloud.enabled():
        rows = cloud._table('activity_logs').select('details').eq('action', action).order('id', desc=True).limit(1).execute().data or []
    else:
        rows = db.query('SELECT details FROM activity_logs WHERE action=? ORDER BY id DESC LIMIT 1', (action,)).to_dict('records')
    return json.loads(rows[0]['details']) if rows else (default or {})


def write_setting(key, value, user):
    require_admin(user)
    # Append-only configuration events are persistent and included in existing backups.
    db.log_action(int(user['id']), 'BOUTIQUE_CONFIG:' + key, json.dumps(value, ensure_ascii=False))


def invoice_settings():
    return read_setting('facturation', {'ninea': '', 'rccm': ''})


def save_invoice_settings(ninea, rccm, user):
    if len(ninea.strip()) > 100 or len(rccm.strip()) > 100:
        raise ValueError('Les identifiants ne doivent pas dépasser 100 caractères.')
    write_setting('facturation', {'ninea': ninea.strip(), 'rccm': rccm.strip()}, user)


def payment_status(total, paid):
    if float(total) - float(paid) <= 0.005:
        return 'Payée'
    return 'Partiellement payée' if float(paid) > 0 else 'Impayée'


def invoice_number(identifier, source='VENTE'):
    return f'FAC-{source}-{int(identifier):06d}'


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value).casefold()) if not unicodedata.combining(c))


def search(term):
    needle = normalized(term.strip())
    if len(needle) < 2:
        return {}
    result = {}
    specs = [('Produits', 'products', ['id','name','category','barcode','stock','sale_price']),
             ('Clients', 'clients', ['id','name','phone','email','address']),
             ('Fournisseurs', 'suppliers', ['id','name','phone','contact']),
             ('Factures des ventes', 'sales', ['id','created_at','client_id','total','paid','due_date']),
             ('Documents', 'documents', ['id','created_at','document_type','client_id','total','status'])]
    clients = {r['id']: r['name'] for r in records('clients')}
    for title, table, columns in specs:
        selected = []
        for row in records(table):
            item = {col: row.get(col, '') for col in columns}
            if table in ('sales', 'documents'):
                item['Client'] = clients.get(row.get('client_id'), 'Comptant')
                if table == 'sales':
                    item['Facture'] = invoice_number(row['id'])
                elif row['document_type'] == 'FACTURE':
                    item['Facture'] = invoice_number(row['id'], 'DOC')
            if any(needle in normalized(v) for v in item.values()):
                selected.append(item)
        if selected:
            labels = {'id':'N°','name':'Nom','category':'Catégorie','barcode':'Code-barres','stock':'Stock','sale_price':'Prix de vente','phone':'Téléphone','email':'E-mail','address':'Adresse','contact':'Contact','created_at':'Date','client_id':'N° client','total':'Total','paid':'Payé','due_date':'Échéance','document_type':'Type','status':'Statut'}
            result[title] = pd.DataFrame(selected).rename(columns=labels)
    return result


def debt_rows(kind, today=None):
    today = today or date.today()
    client = kind == 'clients'
    parties = {r['id']:r['name'] for r in records('clients' if client else 'suppliers')}
    deadlines = {} if client else supplier_deadlines()
    rows = []
    for record in records('sales' if client else 'purchase_orders'):
        rest = max(0, float(record['total']) - float(record['paid']))
        if rest <= .005:
            continue
        due = (record.get('due_date') or '') if client else deadlines.get(str(record['id']), '')
        status = 'Sans échéance' if not due else ('En retard' if str(due)[:10] < today.isoformat() else 'À échéance' if str(due)[:10] == today.isoformat() else 'À venir')
        rows.append({'N°':record['id'], 'Client' if client else 'Fournisseur':parties.get(record.get('client_id' if client else 'supplier_id'), 'Comptant'), 'Total':float(record['total']), 'Payé':float(record['paid']), 'Reste':rest, 'Échéance':str(due)[:10], 'Situation':status})
    return pd.DataFrame(rows, columns=['N°', 'Client' if client else 'Fournisseur', 'Total','Payé','Reste','Échéance','Situation'])


def save_supplier_due(order_id, due, user):
    require_admin(user)
    if not any(r['id'] == order_id for r in records('purchase_orders')):
        raise ValueError('Commande introuvable.')
    # One event per order prevents concurrent edits to different orders overwriting each other.
    write_setting('echeance_fournisseur:' + str(order_id), {'date': due.isoformat() if due else ''}, user)


def supplier_deadlines():
    result = {}
    for row in records('activity_logs'):
        action = row.get('action', '')
        if action.startswith('BOUTIQUE_CONFIG:echeance_fournisseur:'):
            key = action.rsplit(':',1)[1]
            if key not in result or row['id'] > result[key][0]:
                result[key] = (row['id'], json.loads(row['details']).get('date',''))
    return {key:value[1] for key,value in result.items()}


def profit_summary(start, end):
    sales = {r['id']:r for r in records('sales') if start.isoformat() <= str(r['created_at'])[:10] <= end.isoformat()}
    products = {r['id']:r for r in records('products')}
    revenue = sum(float(r['total']) for r in sales.values())
    cost = 0.0
    estimated = 0
    for item in records('sale_items'):
        if item['sale_id'] not in sales:
            continue
        unit = item.get('unit_cost')
        if unit is None:
            unit = products.get(item['product_id'], {}).get('purchase_price', 0) or 0
            estimated += 1
        cost += float(unit) * int(item['quantity'])
    operating = 0.0
    stock_payments = 0.0
    expense_rows = []
    for r in records('expenses'):
        if not start.isoformat() <= str(r['created_at'])[:10] <= end.isoformat():
            continue
        merchandise = str(r['label']).startswith(('Achat stock - ', 'Règlement fournisseur - commande #'))
        amount = float(r['amount'])
        if merchandise:
            stock_payments += amount
        else:
            operating += amount
        expense_rows.append({'Date':r['created_at'], 'Libellé':r['label'], 'Montant':amount, 'Traitement':'Achat de marchandises (hors charges)' if merchandise else 'Charge d’exploitation'})
    commissions = sum(float(r.get('commission_amount') or 0) for r in sales.values())
    return {'revenue':revenue, 'cost':cost, 'gross':revenue-cost, 'operating':operating,
            'commissions':commissions, 'net':revenue-cost-operating-commissions,
            'stock_payments':stock_payments, 'estimated':estimated, 'expenses':pd.DataFrame(expense_rows)}


def reorder_rows(days=30):
    today = date.today()
    sales = {r['id'] for r in records('sales') if 0 <= (today-date.fromisoformat(str(r['created_at'])[:10])).days < days}
    sold = {}
    for item in records('sale_items'):
        if item['sale_id'] in sales:
            sold[item['product_id']] = sold.get(item['product_id'], 0) + int(item['quantity'])
    outstanding = {}
    for item in records('purchase_order_items'):
        remaining = max(0, int(item['quantity'])-int(item['received_quantity']))
        outstanding[item['product_id']] = outstanding.get(item['product_id'], 0) + remaining
    suppliers = {r['id']:r['name'] for r in records('suppliers')}
    rows = []
    for p in records('products'):
        stock, minimum = int(p['stock']), int(p['min_stock'])
        pending = outstanding.get(p['id'], 0)
        target = max(minimum + 1, sold.get(p['id'], 0) + minimum)
        qty = max(0, math.ceil(target-stock-pending))
        if stock <= minimum or qty > 0:
            rows.append({'id':p['id'], 'Produit':p['name'], 'Stock':stock, 'Minimum':minimum, 'En commande':pending,
                         'À commander':qty, 'Coût unitaire':float(p['purchase_price'] or 0),
                         'Fournisseur':suppliers.get(p.get('supplier_id'),'À choisir'), 'supplier_id':p.get('supplier_id'),
                         'Priorité':'Rupture' if stock<=0 else 'Stock faible' if stock<=minimum else 'Prévision'})
    return pd.DataFrame(rows)


def complete_backup():
    # Fail visibly if a table cannot be read rather than label an incomplete archive complete.
    from workflow_service import backup_objects
    bundle = {'format':'boutique-senegal-backup', 'version':2,
            'created_at':datetime.now(timezone.utc).isoformat(),
            'tables':{table:records(table) for table in db.BACKUP_TABLES}}
    bundle['private_documents'] = backup_objects(bundle['tables'])
    return bundle


def validate_backup(bundle):
    if not isinstance(bundle,dict) or bundle.get('format') != 'boutique-senegal-backup' or bundle.get('version') != 2:
        raise ValueError('Format de sauvegarde incompatible.')
    tables = bundle.get('tables')
    if not isinstance(tables,dict) or not tables or set(tables)-set(db.BACKUP_TABLES):
        raise ValueError('Liste de données invalide.')
    for table, rows in tables.items():
        if not isinstance(rows,list) or not all(isinstance(r,dict) for r in rows):
            raise ValueError('Enregistrements invalides : ' + table)
        keys = ('store_id','product_id') if table == 'store_stock' else ('id',)
        identities = [tuple(r.get(k) for k in keys) for r in rows]
        if any(any(v is None for v in key) for key in identities) or len(set(identities)) != len(identities):
            raise ValueError('Identifiants manquants ou dupliqués : ' + table)
    from workflow_service import validate_backup_objects
    validate_backup_objects(bundle)
    return {table:len(rows) for table,rows in tables.items()}
