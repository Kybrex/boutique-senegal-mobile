"""Product lifecycle stored in the existing, backed-up activity journal."""
from contextlib import closing
from difflib import SequenceMatcher
import json
import logging
import re
import unicodedata

import pandas as pd
import db
import cloud_db as cloud

ARCHIVE_PREFIX = 'PRODUIT_ARCHIVE:'
EVENT_PREFIX = 'PRODUIT_EVT:'
EXIT_REASONS = ('Casse', 'Perte', 'Don', 'Usage personnel', 'Correction d’inventaire', 'Autre')


def require_admin(user):
    if not user or user.get('role') != 'admin':
        raise ValueError('Cette action est réservée à l’administrateur.')


def rows(table, filters=None, prefix=None, conn=None):
    allowed = {'activity_logs','products','sale_items','sales','returns','inventory_counts','stock_transfers','purchase_order_items','purchase_orders','stores'}
    if table not in allowed:
        raise ValueError('Table inconnue.')
    filters = filters or {}
    if cloud.enabled() and conn is None:
        result, offset = [], 0
        while True:
            request = cloud._table(table).select('*').order('id')
            for key, value in filters.items():
                request = request.in_(key, value) if isinstance(value,list) else request.eq(key, value)
            if prefix:
                request = request.like('action', prefix + '%')
            batch = request.range(offset, offset + 499).execute().data or []
            result.extend(batch)
            if not batch:
                return result
            offset += len(batch)
    where, params = [], []
    for key, value in filters.items():
        if key not in {'id','product_id','sale_id','action'}:
            raise ValueError('Filtre inconnu.')
        if isinstance(value,list):
            if not value:
                return []
            where.append(f"{key} IN ({','.join('?' for _ in value)})"); params.extend(value)
        else:
            where.append(f'{key}=?'); params.append(value)
    if prefix:
        where.append('action LIKE ?'); params.append(prefix + '%')
    sql = f'SELECT * FROM {table}' + (' WHERE ' + ' AND '.join(where) if where else '') + ' ORDER BY id'
    if conn is not None:
        return [dict(r) for r in conn.execute(sql, params)]
    with closing(db.connection()) as local:
        return [dict(r) for r in local.execute(sql, params)]


def archived_ids(conn=None):
    state = {}
    for row in rows('activity_logs', prefix=ARCHIVE_PREFIX, conn=conn):
        try:
            pid = int(row['action'][len(ARCHIVE_PREFIX):])
            data = json.loads(row['details'])
            if type(data['archived']) is not bool:
                raise ValueError()
            state[pid] = data['archived']
        except (ValueError, TypeError, KeyError) as error:
            raise ValueError('L’état des produits archivés est illisible. Contactez l’administrateur.') from error
    return {pid for pid, archived in state.items() if archived}


def active_frame(frame, conn=None):
    if frame.empty:
        return frame
    return frame.loc[~frame.id.isin(archived_ids(conn))].copy()


def require_active(product_ids, conn=None):
    if {int(pid) for pid in product_ids} & archived_ids(conn):
        raise ValueError('Ce panier contient un produit archivé. Retirez-le ou restaurez sa fiche avant la vente.')


def normalized_name(name):
    value = ''.join(c for c in unicodedata.normalize('NFKD', str(name)) if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[^\W_]+', value.casefold(), re.UNICODE))


def duplicate_candidates(name, exclude_id=None, conn=None):
    normalized = normalized_name(name)
    candidates = []
    if not normalized:
        return candidates
    for row in rows('products', conn=conn):
        if row['id'] == exclude_id:
            continue
        existing = normalized_name(row['name'])
        exact = normalized == existing
        score = SequenceMatcher(None, normalized, existing).ratio()
        if exact or score >= .88:
            candidates.append({'id':int(row['id']), 'name':row['name'], 'exact':exact, 'score':score})
    return sorted(candidates, key=lambda r: (-r['score'], r['id']))[:10]


def validate_name(name, exclude_id=None, conn=None):
    name = str(name).strip()
    if not normalized_name(name) or len(name) > 150:
        raise ValueError('Le nom doit contenir de 1 à 150 caractères utiles.')
    matches = duplicate_candidates(name, exclude_id, conn)
    exact = next((r for r in matches if r['exact']), None)
    if exact:
        raise ValueError(f"Un produit équivalent existe déjà : {exact['name']} (réf. {exact['id']}). Vérifiez aussi les produits archivés.")
    return name


def write_event(product_id, kind, payload, user_id=None, conn=None):
    action = (ARCHIVE_PREFIX if kind == 'archive' else EVENT_PREFIX) + str(int(product_id))
    details = json.dumps(dict(payload, kind=kind), ensure_ascii=False)
    if conn is not None:
        conn.execute('INSERT INTO activity_logs(user_id,action,details) VALUES(?,?,?)', (user_id,action,details))
    elif cloud.enabled():
        cloud._table('activity_logs').insert({'user_id':user_id,'action':action,'details':details}).execute()
    else:
        db.execute('INSERT INTO activity_logs(user_id,action,details) VALUES(?,?,?)', (user_id,action,details))


def product(product_id, conn=None):
    found = rows('products', {'id':int(product_id)}, conn=conn)
    if not found:
        raise ValueError('Produit introuvable.')
    return found[0]


def set_archived(user, product_id, archived, reason):
    require_admin(user)
    reason = str(reason).strip()
    if not reason or len(reason) > 200:
        raise ValueError('Indiquez un motif de 1 à 200 caractères.')
    if cloud.enabled():
        row = product(product_id)
        if (int(product_id) in archived_ids()) == bool(archived):
            raise ValueError('Le statut a déjà changé. Actualisez la liste.')
        write_event(product_id, 'archive', {'archived':bool(archived),'name':row['name'],'reason':reason}, int(user['id']))
    else:
        with closing(db.connection()) as conn, conn:
            conn.execute('BEGIN IMMEDIATE')
            row = product(product_id, conn)
            if (int(product_id) in archived_ids(conn)) == bool(archived):
                raise ValueError('Le statut a déjà changé. Actualisez la liste.')
            write_event(product_id, 'archive', {'archived':bool(archived),'name':row['name'],'reason':reason}, int(user['id']), conn)


def _audit_after_update(product_id, kind, payload, user_id):
    try:
        write_event(product_id, kind, payload, user_id)
    except Exception:
        logging.getLogger(__name__).exception('Product updated but history write failed')
        return 'La modification est enregistrée, mais son ajout à l’historique a échoué. Ne répétez pas l’opération.'
    return None


def update_identity(user, product_id, name, category, expected_name, expected_category):
    require_admin(user)
    category = str(category).strip()
    if len(category) > 100:
        raise ValueError('La catégorie est limitée à 100 caractères.')
    def check(conn=None):
        row = product(product_id, conn)
        if row['name'] != expected_name or (row.get('category') or '') != (expected_category or ''):
            raise ValueError('La fiche a changé. Actualisez avant de la modifier.')
        return row, validate_name(name, int(product_id), conn)
    if cloud.enabled():
        row, name = check()
        request = cloud._table('products').update({'name':name,'category':category}).eq('id',int(product_id)).eq('name',row['name'])
        request = request.is_('category','null') if row.get('category') is None else request.eq('category',row['category'])
        if not (request.execute().data or []):
            raise ValueError('La fiche a changé. Actualisez avant de la modifier.')
        return _audit_after_update(product_id,'identity',{'before':{'name':row['name'],'category':row.get('category')},'after':{'name':name,'category':category}},int(user['id']))
    with closing(db.connection()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        row, name = check(conn)
        conn.execute('UPDATE products SET name=?,category=? WHERE id=?', (name,category,int(product_id)))
        write_event(product_id,'identity',{'before':{'name':row['name'],'category':row.get('category')},'after':{'name':name,'category':category}},int(user['id']),conn)


def change_stock(user, product_id, mode, amount, expected_stock, reason, note=''):
    require_admin(user)
    if mode not in {'Définir','Ajouter','Retirer'} or isinstance(amount,bool) or int(amount) != amount or amount < 0:
        raise ValueError('Mouvement de stock invalide.')
    amount, expected_stock = int(amount), int(expected_stock)
    target = amount if mode == 'Définir' else expected_stock + (amount if mode == 'Ajouter' else -amount)
    if target < 0 or target == expected_stock:
        raise ValueError('Le mouvement doit changer le stock sans le rendre négatif.')
    if target < expected_stock and reason not in EXIT_REASONS:
        raise ValueError('Choisissez le motif de sortie du stock.')
    note = str(note).strip()
    if len(note) > 200 or (reason == 'Autre' and not note):
        raise ValueError('Précisez le motif (200 caractères maximum).')
    payload = {'before':expected_stock,'after':target,'delta':target-expected_stock,'reason':reason if target < expected_stock else 'Entrée / correction','note':note}
    if cloud.enabled():
        require_active([product_id])
        row = product(product_id)
        if int(row['stock']) != expected_stock:
            raise ValueError('Le stock a changé. Actualisez avant de confirmer.')
        if not (cloud._table('products').update({'stock':target}).eq('id',int(product_id)).eq('stock',expected_stock).execute().data or []):
            raise ValueError('Le stock a changé. Actualisez avant de confirmer.')
        warning = None
        try:
            main = cloud._one('stores',name='Boutique principale')
            if main:
                current = cloud._data(cloud._table('store_stock').select('*').eq('store_id',main['id']).eq('product_id',int(product_id)).execute())
                if current:
                    result = cloud._table('store_stock').update({'stock':target}).eq('store_id',main['id']).eq('product_id',int(product_id)).eq('stock',expected_stock).execute().data or []
                    if not result:
                        raise ValueError('Le stock de la boutique a changé.')
                else:
                    cloud._table('store_stock').insert({'store_id':main['id'],'product_id':int(product_id),'stock':target}).execute()
        except Exception:
            logging.getLogger(__name__).exception('Stock changed but store mirror update failed')
            warning = 'Stock du produit enregistré ; la synchronisation avec la boutique doit être vérifiée. Ne répétez pas ce mouvement.'
        audit_warning = _audit_after_update(product_id,'movement',payload,int(user['id']))
        return ' '.join(filter(None,[warning,audit_warning])) or None
    with closing(db.connection()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        require_active([product_id],conn)
        row = product(product_id,conn)
        if int(row['stock']) != expected_stock:
            raise ValueError('Le stock a changé. Actualisez avant de confirmer.')
        conn.execute('UPDATE products SET stock=? WHERE id=?',(target,int(product_id)))
        conn.execute('INSERT INTO store_stock(store_id,product_id,stock) VALUES(1,?,?) ON CONFLICT(store_id,product_id) DO UPDATE SET stock=excluded.stock',(int(product_id),target))
        write_event(product_id,'movement',payload,int(user['id']),conn)
