"""Named catalogue presets stored with existing backed-up configuration events."""
from copy import deepcopy
from datetime import datetime, timezone
import json


class CatalogDataError(ValueError):
    def __init__(self, recovered):
        super().__init__('Un ancien enregistrement de catalogue est incomplet. Rechargez une version disponible ou recomposez le catalogue, puis enregistrez-le à nouveau.')
        self.recovered = recovered


def list_catalogs(user):
    import business_features as features
    features.require_admin(user)
    key = f'catalogues:{int(user["id"])}'
    try:
        value = features.read_setting(key, {})
        if not isinstance(value, dict) or not isinstance(value.get('items', {}), dict):
            raise ValueError('Invalid catalogue data')
        return value.get('items', {})
    except (ValueError, TypeError):
        # Keep every original event. Recover the latest complete snapshot if an
        # old audit-log writer truncated the newest JSON payload.
        action = 'BOUTIQUE_CONFIG:' + key
        if features.cloud.enabled():
            rows = features.cloud._table('activity_logs').select('details').eq('action', action).order('id', desc=True).limit(50).execute().data or []
        else:
            rows = features.db.query('SELECT details FROM activity_logs WHERE action=? ORDER BY id DESC LIMIT 50', (action,)).to_dict('records')
        for row in rows:
            try:
                value = json.loads(row['details'])
                if isinstance(value, dict) and isinstance(value.get('items'), dict):
                    raise CatalogDataError(value['items'])
            except (json.JSONDecodeError, TypeError):
                continue
        raise CatalogDataError({})


def save_catalog(user, name, preset):
    import business_features as features
    features.require_admin(user)
    name = str(name).strip()
    if not name or len(name) > 80:
        raise ValueError('Donnez au catalogue un nom de 1 à 80 caractères.')
    value = deepcopy(preset)
    # Store selections and editorial content, never photos or stale stock/prices.
    value['updated_at'] = datetime.now(timezone.utc).isoformat()
    if len(json.dumps(value, ensure_ascii=False)) > 200000:
        raise ValueError('Ce catalogue contient trop de texte pour être enregistré.')
    try:
        items = list_catalogs(user)
    except CatalogDataError as exc:
        items = exc.recovered
    if name not in items and len(items) >= 50:
        raise ValueError('Vous avez déjà 50 catalogues enregistrés.')
    items[name] = value
    action = f'BOUTIQUE_CONFIG:catalogues:{int(user["id"])}'
    payload = json.dumps({'items':items}, ensure_ascii=False)
    # Do not use log_action: the general audit writer truncates at 500 chars.
    if features.cloud.enabled():
        features.cloud._table('activity_logs').insert({'user_id':int(user['id']), 'action':action, 'details':payload}).execute()
    else:
        features.db.execute('INSERT INTO activity_logs(user_id,action,details) VALUES(?,?,?)', (int(user['id']), action, payload))


def restore_catalog(state, preset, products):
    """Restore before widget creation; discard products no longer in the database."""
    from datetime import date
    options = deepcopy(preset.get('options', {}))
    valid_ids = {int(x) for x in products.id} if not products.empty else set()
    selected = [int(x) for x in preset.get('product_ids', []) if int(x) in valid_ids]
    for key in list(state):
        if key.startswith('catalog_') and key not in ('catalog_library_choice',):
            del state[key]
    state['catalog_stock'] = bool(preset.get('only_stock', True))
    state['catalog_products'] = selected
    categories = products.Categorie.fillna('').replace('', 'Autres produits') if not products.empty else []
    state['catalog_categories'] = sorted(set(categories[products.id.isin(selected)])) if len(categories) else []
    state['catalog_whatsapp'] = options.get('whatsapp', '')
    expiry = options.get('valid_until')
    if expiry:
        state['catalog_expiry'] = max(date.today(), date.fromisoformat(expiry))
    for option, key, default in [('show_prices','catalog_show_prices',True), ('cover','catalog_cover',True),
                                 ('title','catalog_title','Catalogue produits'), ('delivery_zones','catalog_zones',''),
                                 ('delivery_fees','catalog_fees',''), ('delivery_times','catalog_times','')]:
        state[key] = options.get(option, default)
    state['catalog_saved_options'] = options
    return len(preset.get('product_ids', [])) - len(selected)
