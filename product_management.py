"""Delete unused products without removing business history."""
import logging
from contextlib import closing

import db
import cloud_db as cloud


LINKED_TABLES = (
    ('sale_items', 'des ventes'),
    ('document_items', 'des devis ou factures'),
    ('purchase_order_items', 'des commandes fournisseurs'),
    ('returns', 'des retours'),
    ('inventory_counts', 'des inventaires'),
    ('stock_transfers', 'des transferts de stock'),
    ('product_lots', 'des lots'),
    ('product_variants', 'des variantes'),
)


def delete_product(user, product_id, expected_stock, reason):
    if not user or user.get('role') != 'admin':
        raise ValueError('Seul un administrateur peut supprimer un produit.')
    reason = str(reason).strip()
    if not reason or len(reason) > 200:
        raise ValueError('Indiquez un motif de 1 à 200 caractères.')
    product_id = int(product_id)
    if cloud.enabled():
        product = cloud._one('products', id=product_id)
        _check_product(product, expected_stock)
        for table, label in LINKED_TABLES:
            if cloud._data(cloud._table(table).select('id').eq('product_id', product_id).limit(1).execute()):
                raise ValueError(f'Ce produit est lié à {label} : suppression impossible pour préserver cet historique.')
        main = cloud._one('stores', name='Boutique principale')
        stocks = cloud._data(cloud._table('store_stock').select('store_id,stock').eq('product_id', product_id).execute())
        _check_stores(stocks, main['id'] if main else None)
        try:
            # One DELETE: the existing foreign keys protect history even if a sale
            # is created after the checks. Only store_stock cascades here.
            removed = cloud._data(cloud._table('products').delete().eq('id', product_id).eq('stock', int(expected_stock)).execute())
        except Exception as error:
            if getattr(error, 'code', None) == '23503':
                raise ValueError('Ce produit possède un historique et ne peut pas être supprimé.') from error
            raise
        if not removed:
            raise ValueError('Le produit ou son stock a changé. Actualisez avant de confirmer à nouveau.')
        try:
            db.log_action(int(user['id']), 'PRODUIT_SUPPRIME', _details(product, reason))
        except Exception:
            logging.getLogger(__name__).exception('Product deleted but audit write failed')
            return 'Produit supprimé, mais son inscription au journal a échoué.'
        return None

    with closing(db.connection()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        product = conn.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
        _check_product(product, expected_stock)
        for table, label in LINKED_TABLES:
            if conn.execute(f'SELECT 1 FROM {table} WHERE product_id=? LIMIT 1', (product_id,)).fetchone():
                raise ValueError(f'Ce produit est lié à {label} : suppression impossible pour préserver cet historique.')
        main = conn.execute("SELECT id FROM stores WHERE name='Boutique principale'").fetchone()
        stocks = conn.execute('SELECT store_id,stock FROM store_stock WHERE product_id=?', (product_id,)).fetchall()
        _check_stores(stocks, main['id'] if main else None)
        conn.execute('INSERT INTO activity_logs(user_id,action,details) VALUES(?,?,?)',
                     (int(user['id']), 'BOUTIQUE_CONFIG:product_id_high_watermark', str(product_id)))
        conn.execute('DELETE FROM store_stock WHERE product_id=?', (product_id,))
        conn.execute('DELETE FROM products WHERE id=?', (product_id,))
        conn.execute('INSERT INTO activity_logs(user_id,action,details) VALUES(?,?,?)',
                     (int(user['id']), 'PRODUIT_SUPPRIME', _details(product, reason)))
    return None


def _check_product(product, expected_stock):
    if product is None:
        raise ValueError('Produit introuvable ou déjà supprimé.')
    if int(product['stock']) != int(expected_stock):
        raise ValueError('Le stock a changé. Actualisez avant de confirmer à nouveau.')


def _check_stores(stocks, main_id):
    if any(row['store_id'] != main_id and int(row['stock']) != 0 for row in stocks):
        raise ValueError('Ce produit possède du stock dans une autre boutique. Réglez ce stock avant de le supprimer.')


def _details(product, reason):
    return f"{product['name']} (#{product['id']}), stock supprimé : {product['stock']}; {reason}"
