"""Read-only product history; quantities are movements, not a reconstructed balance."""
import json
import re
import pandas as pd
from product_lifecycle import rows, product, EVENT_PREFIX, ARCHIVE_PREFIX


def history(product_id):
    pid = int(product_id)
    current = product(pid)
    result = []
    def add(when, kind, quantity, detail, reference='', actor=''):
        result.append({'Date':when or '', 'Événement':kind, 'Quantité':quantity,
                       'Détail':detail, 'Référence':reference, 'Utilisateur':str(actor or '')})
    add(current.get('created_at'),'Création',None,'Création de la fiche ; quantité initiale non reconstituée.',f'Produit #{pid}')
    events = rows('activity_logs', {'action':[EVENT_PREFIX+str(pid),ARCHIVE_PREFIX+str(pid)]})
    receipt_items = {}
    for event in events:
        data = json.loads(event['details'])
        kind = data.get('kind')
        when, actor = event.get('created_at'), event.get('user_id')
        if kind == 'archive':
            add(when,'Archivage' if data['archived'] else 'Restauration',None,data.get('reason',''),actor=actor)
        elif kind == 'identity':
            old,new = data['before'],data['after']
            add(when,'Fiche modifiée',None,f"{old['name']} → {new['name']} ; catégorie : {old.get('category') or '—'} → {new.get('category') or '—'}",actor=actor)
        elif kind == 'movement':
            add(when,'Sortie' if data['delta'] < 0 else 'Entrée / correction',data['delta'],f"{data['reason']} — {data.get('note','')} (stock {data['before']} → {data['after']})",actor=actor)
        elif kind == 'purchase':
            add(when,'Achat reçu',data['quantity'],data.get('supplier',''),actor=actor)
        elif kind == 'receipt':
            receipt_items[int(data['item_id'])] = receipt_items.get(int(data['item_id']),0)+int(data['quantity'])
            add(when,'Réception fournisseur',data['quantity'],'Quantité reçue',f"Commande #{data['order_id']}",actor)
    returns = rows('returns',{'product_id':pid})
    sold = {}
    for item in rows('sale_items',{'product_id':pid}):
        sold[item['sale_id']] = sold.get(item['sale_id'],0) + int(item['quantity'])
    # Returns reduce/delete sale_items in this app. Add their quantities back
    # to show the original sale, then show the return as its own positive row.
    for item in returns:
        sold[item['sale_id']] = sold.get(item['sale_id'],0) + int(item['quantity'])
        add(item.get('created_at'),'Retour',int(item['quantity']),item.get('reason',''),f"Vente #{item['sale_id']}",item.get('processed_by'))
    for sale in rows('sales',{'id':list(sold)}) if sold else []:
        add(sale.get('created_at'),'Vente',-sold[sale['id']],f"Boutique #{sale.get('store_id') or 1}",f"Vente #{sale['id']}",f"Vendeur #{sale.get('seller_id')}")
    for item in rows('inventory_counts',{'product_id':pid}):
        add(item.get('created_at'),'Inventaire',int(item['difference']),f"{item['expected_stock']} → {item['counted_stock']} ; {item.get('notes','')}",f"Inventaire #{item['id']}",item.get('counted_by'))
    for item in rows('stock_transfers',{'product_id':pid}):
        add(item.get('created_at'),'Transfert',None,f"{item['quantity']} unité(s), boutique #{item['from_store_id']} → #{item['to_store_id']} ; {item.get('notes','')}",f"Transfert #{item['id']}",item.get('transferred_by'))
    for item in rows('purchase_order_items',{'product_id':pid}):
        old_quantity = int(item.get('received_quantity') or 0)-receipt_items.get(item['id'],0)
        if old_quantity > 0:
            add('', 'Anciennes réceptions',None,f"Cumul ancien reçu : {old_quantity} unité(s). Dates détaillées non enregistrées.",f"Commande #{item['purchase_order_id']}")
    legacy = rows('activity_logs',{'action':['STOCK_MODIFIE','PRIX_MODIFIES','PRODUIT_SUPPRIME']})
    pattern = re.compile(r'\(#'+str(pid)+r'\)')
    for event in legacy:
        if pattern.search(event.get('details') or ''):
            add(event.get('created_at'),'Ancienne modification',None,event['details'],actor=event.get('user_id'))
    frame = pd.DataFrame(result)
    frame['_sort'] = pd.to_datetime(frame.Date,utc=True,errors='coerce',format='mixed')
    return frame.sort_values('_sort',ascending=False,na_position='last',kind='stable').drop(columns='_sort').reset_index(drop=True)
