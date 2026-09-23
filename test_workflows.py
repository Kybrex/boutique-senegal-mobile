"""Regression checks using isolated SQLite and private temporary storage."""
from copy import deepcopy
from datetime import date, timedelta
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import gc
import pandas as pd
from PIL import Image
from pypdf import PdfReader
import db
import v3_db as v3
import v4_db as v4
import business_features as features
import workflow_service as service

def rejects(action):
    try:
        action()
    except (ValueError, KeyError, OSError):
        return
    raise AssertionError('Expected rejection')

def run():
    with TemporaryDirectory() as folder:
        db.DB_PATH=Path(folder)/'boutique.db'
        db.init_db()
        db.create_user('admin','Administrateur','test-password','admin')
        user=db.authenticate('admin','test-password')
        db.create_seller_with_user('Vendeur','','','seller','test-password')
        seller=db.authenticate('seller','test-password')
        db.add_client('Client Alpha','77 123 45 67','alpha@example.test','Dakar')
        db.add_client('Client Beta','','','')
        db.add_supplier('Fournisseur','','','','')
        db.add_product('Riz','Épicerie',500,1000,200,5,1)
        today=date.today()
        sale,_,_=db.save_sale([{'id':1,'quantity':2,'sale_price':1000}],1,1,500,'Espèces',0,today)
        db.add_credit_payment(1,sale,400,'Wave',user['id'])
        env=service.issue_invoice('VENTE',sale,user)
        assert set(env['files'])=={'A4','A5'}
        pdf,name,_=service.unpack_file(env,'A4')
        text=''.join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
        assert 'Client Alpha' in text and 'Reste à payer' not in text and 'Échéance' not in text
        db.update_sale(sale,1,1500,'Espèces',200)
        db.update_settings('Nouveau nom','999','Autre adresse','','')
        again=service.issue_invoice('VENTE',sale,user)
        assert service.unpack_file(again,'A4')[0]==pdf
        assert len(service.entries(user))==1
        docid=v3.create_document('FACTURE',1,None,'', [{'product_id':1,'quantity':1,'unit_price':1000}],user['id'])
        service.issue_invoice('DOC',docid,user)
        assert len(service.entries(user))==2
        rejects(lambda:service.issue_invoice('VENTE',sale,seller))
        rejects(lambda:service.entries(seller))
        rejects(lambda:service.read_object('../../secrets'))
        rejects(lambda:service.write_object_once('documents-v1/../evil.json',b'x'))
        # Restoring payment totals to test the initial-versus-later split.
        db.update_sale(sale,1,900,'Espèces',0)
        profile=service.client_profile(1,user)
        assert profile['debt']==1100
        assert sum(r['Montant'] for r in profile['payments'])==900
        assert len(profile['invoices'])==2
        assert service.client_profile(2,user)['invoices']==[]
        rejects(lambda:service.client_profile(1,seller))
        db.add_expense('Transport',500)
        image=BytesIO(); Image.new('RGB',(80,50),'white').save(image,format='PNG')
        attachment=service.add_attachment('expenses',1,'../reçu.png',image.getvalue(),'Taxi',user)
        duplicate=service.add_attachment('expenses',1,'reçu.png',image.getvalue(),'Taxi',user)
        assert attachment['key']==duplicate['key']
        assert attachment['filename']=='reçu.png'
        rejects(lambda:service.add_attachment('expenses',1,'bad.jpg',b'not an image','',user))
        rejects(lambda:service.add_attachment('expenses',1,'huge.pdf',b'x'*(service.MAX_FILE+1),'',user))
        rejects(lambda:service.add_attachment('expenses',999,'recu.png',image.getvalue(),'',user))
        assert service.whatsapp_url('77 123 45 67','Bonjour & merci').startswith('https://wa.me/221771234567?text=Bonjour%20%26')
        assert service.whatsapp_url('00221771234567','Bonjour').startswith('https://wa.me/221771234567')
        rejects(lambda:service.whatsapp_url('javascript:alert(1)','a'))
        rejects(lambda:service.whatsapp_url('123','a'))
        bundle=features.complete_backup()
        assert len(bundle['private_documents'])==3
        assert len(features.validate_backup(bundle))==len(db.BACKUP_TABLES)
        missing=deepcopy(bundle); missing['private_documents'].pop(next(iter(missing['private_documents'])))
        rejects(lambda:features.validate_backup(missing))
        corrupt=deepcopy(bundle); next(iter(corrupt['private_documents'].values()))['sha256']='wrong'
        rejects(lambda:features.validate_backup(corrupt))
        legacy={'format':'boutique-senegal-backup','version':2,'tables':{'clients':[]}}
        assert features.validate_backup(legacy)=={'clients':0}
        assert service.backup_status()['due']
        service.record_backup('prepared','a'*64,service.now_iso(),user)
        assert service.backup_status()['due']  # Preparing alone is not a retained copy.
        service.record_backup('confirmed','a'*64,service.now_iso(),user)
        assert not service.backup_status()['due']
        service.save_preferences(3,2,user)
        assert service.preferences()=={'idle_minutes':3,'backup_days':2}
        rejects(lambda:service.save_preferences(3,2,seller))
        rejects(lambda:service.save_preferences(0,2,user))
        assert v4.automatic_backup_if_due(user)=='créée et vérifiée'
        assert service.backup_status()['automatic_verified']
        assert v4.automatic_backup_if_due(user)=='à jour'
        # Recover into a fresh database, including PDFs and image bytes.
        db.DB_PATH=Path(folder)/'restored'/'boutique.db'; db.DB_PATH.parent.mkdir()
        db.init_db()
        db.restore_backup(bundle)
        restored_admin=db.authenticate('admin','test-password')
        restored=service.get_document(env['meta']['key'],restored_admin)
        assert service.unpack_file(restored,'A4')[0]==pdf
        assert len(service.entries(restored_admin))==3
        assert sum(db.restore_backup(bundle).values())==0
        # No public bucket can be used accidentally.
        class PublicStorage:
            def get_bucket(self,name): return {'public':True}
        class Client:
            storage=PublicStorage()
        with patch.object(service.cloud,'client',return_value=Client()):
            rejects(service._bucket)
        gc.collect()
    print('PASS: immutable invoices, A4/A5, document invoices, role checks, private attachments, client totals, WhatsApp preparation, backup integrity and recovery, reminders, automatic backups')

if __name__=='__main__':
    run()
