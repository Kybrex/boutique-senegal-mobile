"""Catalogue-only prices, references and order links."""
from datetime import date
import math
import re
from urllib.parse import quote


def whatsapp_number(value):
    value = str(value or '').strip()
    if not value:
        return ''
    if re.search(r'[^0-9+().\s-]', value):
        raise ValueError('Numéro WhatsApp invalide.')
    digits = re.sub(r'\D', '', value)
    if digits.startswith('00'):
        digits = digits[2:]
    if len(digits) == 9:
        digits = '221' + digits
    if not 10 <= len(digits) <= 15 or digits.startswith('0'):
        raise ValueError('Indiquez un numéro WhatsApp avec indicatif pays, par exemple +221 77 123 45 67.')
    return digits


def order_link(number, message='Bonjour, je souhaite commander un produit du catalogue.'):
    number = whatsapp_number(number)
    return 'https://wa.me/' + number + '?text=' + quote(message) if number else ''


def reference(row):
    code = row.get('Code_barres')
    if isinstance(code, str) and code.strip():
        return code.strip()
    identifier = row.get('id')
    if identifier is not None and str(identifier) != 'nan':
        return f'PROD-{int(identifier):06d}'
    return ''


def prepare_catalog(products, options):
    result = products.copy()
    result['Categorie'] = result.get('Categorie', '').fillna('').astype(str).str.strip() if 'Categorie' in result else ''
    result['Categorie'] = result['Categorie'].replace('', 'Autres produits')
    promotions = options.get('promotions', {}) if options.get('show_prices', True) else {}
    valid_until = options.get('valid_until')
    if valid_until and date.fromisoformat(str(valid_until)) < date.today():
        raise ValueError('La date de validité est dépassée. Choisissez une date actuelle ou future.')
    prices = []
    for _, row in result.iterrows():
        key = str(int(row['id'])) if 'id' in row else ''
        value = promotions.get(key)
        if value is None or value == '':
            prices.append(None)
            continue
        value = float(value)
        if not math.isfinite(value) or not 0 < value < float(row['Vente']):
            raise ValueError(f"Le prix promotionnel de {row['Produit']} doit être positif et inférieur au prix normal.")
        prices.append(value)
    result['Promo'] = prices
    result['Reference'] = [reference(row) for _, row in result.iterrows()]
    details = options.get('details', {})
    for field, limit in [('Description', 300), ('Tailles', 100), ('Couleurs', 100)]:
        values = []
        for _, row in result.iterrows():
            key = str(int(row['id'])) if 'id' in row else ''
            value = str(details.get(key, {}).get(field, '') or '').strip()
            if len(value) > limit:
                raise ValueError(f'{field} : limitez le texte à {limit} caractères par produit.')
            values.append(value)
        result[field] = values
    for field in ('delivery_zones', 'delivery_fees', 'delivery_times'):
        if len(str(options.get(field, ''))) > 300:
            raise ValueError('Limitez chaque condition de livraison à 300 caractères.')
    return result.sort_values(['Categorie', 'Produit'], kind='stable') if not result.empty else result
