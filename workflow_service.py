"""Private document storage, immutable invoice copies and daily workflows.

Metadata uses append-only activity events; binary files use private JSON objects.
No public URL is generated, and a failed write is never reported as archived.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from urllib.parse import quote
import pandas as pd
import db
import cloud_db as cloud
import business_features as features

BUCKET = 'automatic-backups'
PREFIX = 'documents-v1/'
EVENT = 'BOUTIQUE_DOCUMENT_V1'
MAX_FILE = 5 * 1024 * 1024
MAX_BACKUP = 100 * 1024 * 1024

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode('utf-8')

def preferences():
    saved = features.read_setting('quotidien', {})
    return {'idle_minutes': max(1, min(60, int(saved.get('idle_minutes', 5)))),
            'backup_days': max(1, min(30, int(saved.get('backup_days', 7))))}

def save_preferences(idle_minutes, backup_days, user):
    features.require_admin(user)
    if not 1 <= int(idle_minutes) <= 60 or not 1 <= int(backup_days) <= 30:
        raise ValueError('Délai invalide.')
    features.write_setting('quotidien', {'idle_minutes':int(idle_minutes), 'backup_days':int(backup_days)}, user)

def _key(key):
    if not isinstance(key, str) or not re.fullmatch(r'documents-v1/(invoices/(VENTE|DOC)/[1-9][0-9]*|attachments/[a-f0-9]{32})\.json', key):
        raise ValueError('Référence de fichier invalide.')
    return key

def _bucket():
    # This bucket already belongs to the app. Never reuse public product images.
    storage = cloud.client().storage
    bucket = storage.get_bucket(BUCKET)
    public = bucket.get('public') if isinstance(bucket, dict) else getattr(bucket, 'public', None)
    if public is not False:
        raise ValueError('Le stockage des documents doit être privé.')
    return storage.from_(BUCKET)

def _local_path(key):
    return Path(db.DB_PATH).parent / 'private_documents' / _key(key)

def read_object(key):
    _key(key)
    if cloud.enabled():
        return bytes(_bucket().download(key))
    return _local_path(key).read_bytes()

def write_object_once(key, data):
    """Create-only write; return the winner's bytes for concurrent first issues."""
    _key(key)
    if cloud.enabled():
        bucket = _bucket()
        try:
            bucket.upload(key, data, {'content-type':'application/json', 'upsert':'false'})
        except Exception as error:
            # A duplicate is safe only when an existing valid object can be read.
            try:
                return bytes(bucket.download(key))
            except Exception:
                raise ValueError('Enregistrement privé impossible. Réessayez après vérification du stockage.') from error
        saved = bytes(bucket.download(key))
        if saved != data:
            raise ValueError('Le contrôle du fichier enregistré a échoué.')
        return saved
    path = _local_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Link the complete temporary file atomically; readers never see a partial PDF.
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        try:
            os.link(temp_path, path)
        except FileExistsError:
            pass
    finally:
        temp_path.unlink()
    return path.read_bytes()

def entries(user):
    features.require_admin(user)
    if cloud.enabled():
        rows, offset = [], 0
        while True:
            batch = cloud._table('activity_logs').select('id,details').eq('action', EVENT).order('id').range(offset, offset+199).execute().data or []
            rows.extend(batch)
            if not batch:
                break
            offset += len(batch)
    else:
        rows = db.query('SELECT id,details FROM activity_logs WHERE action=? ORDER BY id', (EVENT,)).to_dict('records')
    result = {}
    for row in rows:
        item = json.loads(row['details'])
        _key(item['key'])
        result.setdefault(item['key'], item)
    return sorted(result.values(), key=lambda r:r['created_at'], reverse=True)

def _index(meta, user):
    if not any(e['key'] == meta['key'] for e in entries(user)):
        db.log_action(int(user['id']), EVENT, encode(meta).decode('utf-8'))

def _one(table, identifier):
    if table not in ('sales','documents','clients','expenses','purchase_orders'):
        raise ValueError('Type inconnu.')
    if cloud.enabled():
        rows = cloud._table(table).select('*').eq('id', int(identifier)).limit(1).execute().data or []
    else:
        rows = db.query(f'SELECT * FROM {table} WHERE id=?', (int(identifier),)).to_dict('records')
    if not rows:
        raise ValueError('Enregistrement introuvable.')
    return rows[0]

def invoice_source(source, identifier):
    import v3_db as v3
    if source not in ('VENTE','DOC') or int(identifier) < 1:
        raise ValueError('Facture invalide.')
    if source == 'VENTE':
        sale, items = db.sale_details(int(identifier))
        client = _one('clients', sale['client_id']) if sale.get('client_id') else {}
        document = {'id':features.invoice_number(identifier), 'Type':'FACTURE',
                    'Client':client.get('name','Comptant'), 'Date':sale['created_at'], 'Total':sale['total'],
                    'Notes':f"Remise : {float(sale.get('discount') or 0):,.0f} FCFA".replace(',', ' ') if sale.get('discount') else ''}
        client_id = sale.get('client_id')
    else:
        document, items = v3.document_details(int(identifier))
        if document.get('document_type', document.get('Type')) != 'FACTURE':
            raise ValueError('Ce document n’est pas une facture.')
        client_id = document.get('client_id')
        client = _one('clients', client_id) if client_id else {}
    settings = dict(db.get_settings(), **features.invoice_settings())
    return document, items, settings, client_id, client.get('phone', '')

def validate_envelope(raw, key):
    _key(key)
    if len(raw) > 20*1024*1024:
        raise ValueError('Document archivé trop volumineux.')
    envelope = json.loads(raw)
    meta = envelope['meta']
    if envelope.get('version') != 1 or meta.get('key') != key:
        raise ValueError('Archive de document invalide.')
    files = envelope.get('files', {})
    expected = {'A4','A5'} if meta.get('kind') == 'invoice' else {'original'}
    if set(files) != expected:
        raise ValueError('Fichiers de l’archive incomplets.')
    for entry in files.values():
        data = base64.b64decode(entry['data'], validate=True)
        if not data or digest(data) != entry['sha256']:
            raise ValueError('Le contrôle d’intégrité du document a échoué.')
    return envelope

def _packed(data, filename, mime):
    return {'data':base64.b64encode(data).decode('ascii'), 'sha256':digest(data), 'filename':filename, 'mime':mime}

def issue_invoice(source, identifier, user):
    features.require_admin(user)
    key = _key(f'{PREFIX}invoices/{source}/{int(identifier)}.json')
    existing = next((e for e in entries(user) if e['key'] == key), None)
    if existing:
        return validate_envelope(read_object(key), key)
    from business_pdf import make_business_document_pdf
    document, items, settings, client_id, phone = invoice_source(source, identifier)
    number = features.invoice_number(identifier, source)
    meta = {'key':key, 'kind':'invoice', 'source':source, 'source_id':int(identifier),
            'number':number, 'client_id':int(client_id) if client_id else None,
            'client':str(document.get('Client') or 'Comptant'), 'phone':str(phone or ''),
            'total':float(document.get('Total', document.get('total', 0))), 'created_at':now_iso()}
    envelope = {'version':1, 'meta':meta, 'snapshot':{'document':document, 'settings':settings,
                'items':items.to_dict('records')}, 'files':{}}
    for fmt in ('A4','A5'):
        pdf = make_business_document_pdf(document, items, settings, paper_format=fmt)
        envelope['files'][fmt] = _packed(pdf, f'{number}_{fmt}.pdf', 'application/pdf')
    saved = validate_envelope(write_object_once(key, encode(envelope)), key)
    _index(saved['meta'], user)
    return saved

def get_document(key, user):
    features.require_admin(user)
    if not any(e['key'] == key for e in entries(user)):
        raise ValueError('Document non référencé.')
    return validate_envelope(read_object(key), key)

def unpack_file(envelope, name):
    entry = envelope['files'][name]
    data = base64.b64decode(entry['data'], validate=True)
    if digest(data) != entry['sha256']:
        raise ValueError('Fichier endommagé.')
    return data, entry['filename'], entry['mime']

def validate_attachment(data, filename):
    if not data or len(data) > MAX_FILE:
        raise ValueError('Choisissez un fichier de 5 Mo maximum.')
    ext = Path(filename).suffix.lower()
    if ext == '.pdf' and data.startswith(b'%PDF-'):
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 100:
            raise ValueError('PDF protégé ou trop long : maximum 100 pages.')
        mime = 'application/pdf'
    elif ext in ('.jpg','.jpeg','.png'):
        from PIL import Image
        with Image.open(BytesIO(data)) as img:
            if img.format not in ('JPEG','PNG') or img.width*img.height > 25_000_000:
                raise ValueError('Image trop grande ou format non pris en charge.')
            img.verify()
        mime = 'image/png' if data.startswith(b'\x89PNG') else 'image/jpeg'
    else:
        raise ValueError('Formats acceptés : PDF, JPG ou PNG.')
    clean = re.sub(r'[^\w. -]', '_', Path(filename.replace('\\','/')).name)[:100]
    return clean or 'justificatif'+ext, mime

def add_attachment(target, identifier, filename, data, note, user):
    features.require_admin(user)
    if target not in ('expenses','purchase_orders'):
        raise ValueError('Destination invalide.')
    record = _one(target, identifier)
    name, mime = validate_attachment(data, filename)
    sha = digest(data)
    for item in entries(user):
        if item.get('kind') == 'attachment' and item.get('target') == target and item.get('source_id') == int(identifier) and item.get('sha256') == sha:
            return item
    key = f'{PREFIX}attachments/{uuid4().hex}.json'
    meta = {'key':key, 'kind':'attachment', 'target':target, 'source_id':int(identifier),
            'filename':name, 'note':str(note)[:500], 'sha256':sha, 'created_at':now_iso(),
            'label':record.get('label', f'Commande #{identifier}')}
    envelope = {'version':1, 'meta':meta, 'files':{'original':_packed(data,name,mime)}}
    saved = validate_envelope(write_object_once(key, encode(envelope)), key)
    _index(saved['meta'], user)
    return saved['meta']

def whatsapp_url(phone, message):
    raw = str(phone).strip()
    if re.search(r'[^0-9+(). \-]', raw):
        raise ValueError('Numéro de téléphone invalide.')
    digits = re.sub(r'\D', '', raw)
    if digits.startswith('00'):
        digits = digits[2:]
    elif len(digits) == 9 and not raw.startswith('+'):
        digits = '221'+digits
    if not 8 <= len(digits) <= 15 or digits.startswith('0'):
        raise ValueError('Saisissez le numéro avec son indicatif, par exemple +221…')
    if not str(message).strip() or len(message) > 2000:
        raise ValueError('Le message doit contenir entre 1 et 2 000 caractères.')
    return 'https://wa.me/'+digits+'?text='+quote(message, safe='')

def client_profile(identifier, user):
    features.require_admin(user)
    client = _one('clients', identifier)
    def related(table):
        return [r for r in features.records(table) if r.get('client_id') == int(identifier)]
    sales, payments, documents = related('sales'), related('credit_payments'), related('documents')
    paid_later = {}
    for payment in payments:
        sid = payment.get('sale_id')
        paid_later[sid] = paid_later.get(sid, 0)+float(payment['amount'])
    timeline = [{'Date':r['created_at'], 'Vente':r.get('sale_id'), 'Montant':float(r['amount']),
                 'Mode':r.get('payment_method',''), 'Origine':'Règlement ultérieur'} for r in payments]
    for sale in sales:
        initial = max(0, float(sale['paid'])-paid_later.get(sale['id'], 0))
        if initial:
            timeline.append({'Date':sale['created_at'], 'Vente':sale['id'], 'Montant':initial,
                             'Mode':sale.get('payment_method',''), 'Origine':'À la vente'})
    return {'client':client, 'sales':sales, 'payments':sorted(timeline,key=lambda r:str(r['Date']),reverse=True),
            'documents':documents, 'invoices':[e for e in entries(user) if e.get('kind')=='invoice' and e.get('client_id')==int(identifier)],
            'total':sum(float(r['total']) for r in sales),
            'debt':sum(max(0,float(r['total'])-float(r['paid'])) for r in sales)}

def referenced_keys(tables):
    return {json.loads(r['details'])['key'] for r in tables.get('activity_logs', []) if r.get('action') == EVENT}

def backup_objects(tables):
    objects = {}
    for key in sorted(referenced_keys(tables)):
        data = read_object(key)
        validate_envelope(data, key)
        objects[key] = _packed(data, key.rsplit('/',1)[-1], 'application/json')
    return objects

def validate_backup_objects(bundle):
    references = referenced_keys(bundle['tables'])
    objects = bundle.get('private_documents', {})
    if not isinstance(objects, dict) or set(objects) != references:
        raise ValueError('La sauvegarde ne contient pas tous les PDF et justificatifs référencés.')
    total = 0
    for key, obj in objects.items():
        data = base64.b64decode(obj['data'], validate=True)
        total += len(data)
        if total > MAX_BACKUP or digest(data) != obj['sha256']:
            raise ValueError('Sauvegarde trop volumineuse ou fichier endommagé.')
        validate_envelope(data, key)

def restore_objects(bundle):
    validate_backup_objects(bundle)
    for key, item in bundle.get('private_documents', {}).items():
        data = base64.b64decode(item['data'], validate=True)
        if write_object_once(key, data) != data:
            raise ValueError('Un document différent existe déjà. Aucun original ne sera remplacé.')

def restore_indexes(bundle):
    # Event IDs may already belong to unrelated rows on the destination database.
    existing = referenced_keys({'activity_logs':features.records('activity_logs')})
    for row in bundle['tables'].get('activity_logs', []):
        if row.get('action') == EVENT:
            key = json.loads(row['details'])['key']
            if key not in existing:
                db.log_action(None, EVENT, row['details'])
                existing.add(key)

def record_backup(stage, sha, created_at, user):
    if stage not in ('prepared','confirmed','verified','automatic_verified'):
        raise ValueError('État de sauvegarde invalide.')
    features.write_setting('sauvegarde:'+stage, {'at':now_iso(),'sha256':sha,'backup_created_at':created_at}, user)

def backup_status():
    states = {stage:features.read_setting('sauvegarde:'+stage,{}) for stage in ('prepared','confirmed','verified','automatic_verified')}
    saved = [states[s].get('backup_created_at') for s in ('confirmed','automatic_verified') if states[s].get('backup_created_at')]
    latest = max(saved) if saved else None
    due = True
    if latest:
        moment = datetime.fromisoformat(latest.replace('Z','+00:00'))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        due = datetime.now(timezone.utc)-moment >= timedelta(days=preferences()['backup_days'])
    return {**states, 'latest':latest, 'due':due}
