from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date
from unittest.mock import patch
from types import SimpleNamespace
import gc, time, sys
from streamlit.testing.v1 import AppTest
import db, workflow_service as service

def clean(at):
    assert not at.exception, [e.message for e in at.exception]
    assert not at.error, [e.value for e in at.error]

def button(at,label):
    return next(b for b in at.button if b.label==label)

def run():
    with TemporaryDirectory() as folder:
        db.DB_PATH=Path(folder)/'test.db'
        db.init_db()
        db.create_user('admin','Test Admin','test-password','admin')
        db.create_seller_with_user('Vendeur','','','seller','test-password')
        db.add_client('Client Test','771234567','','')
        db.add_supplier('Fournisseur','','','','')
        db.add_product('Riz','Alimentaire',500,1000,30,2,1)
        db.add_expense('Transport',500)
        db.save_sale([{'id':1,'quantity':2,'sale_price':1000}],1,1,500,'Espèces',0,date.today())
        user=db.authenticate('admin','test-password')
        at=AppTest.from_file('iphone_app.py',default_timeout=30).run()
        clean(at)
        next(w for w in at.text_input if w.label=="Nom d'utilisateur").set_value('admin')
        next(w for w in at.text_input if w.label=='Mot de passe').set_value('test-password')
        button(at,'Se connecter').click().run()
        clean(at)
        assert at.session_state['mobile_user']['role']=='admin'
        assert at.session_state['_auth_timeout']==300
        for route in ['Archives factures','Justificatifs','Fiche client','Sauvegardes','Sécurité']:
            at.session_state['mobile_page']=route
            at.run()
            clean(at)
        at.session_state['mobile_receipt_pdf']=b'secret receipt'
        at.session_state['_auth_seen']=time.monotonic()-301
        at.run()
        clean(at)
        assert 'mobile_user' not in at.session_state
        assert 'mobile_receipt_pdf' not in at.session_state
        assert any(w.label=='Mot de passe' for w in at.text_input)
        invoice=AppTest.from_string("import workflow_ui; workflow_ui.invoice_panel('VENTE',1,"+repr(user)+")",default_timeout=30).run()
        clean(invoice)
        button(invoice,'Émettre et archiver la facture').click().run()
        clean(invoice)
        assert len(service.entries(user))==1
        next(w for w in invoice.radio if w.label=='Format d’impression').set_value('A5').run()
        clean(invoice)
        assert not invoice.get('link_button')
        invoice.checkbox[0].check().run()
        clean(invoice)
        assert len(invoice.get('link_button'))==1
        backup=AppTest.from_string("import workflow_ui; workflow_ui.backups_page("+repr(user)+")",default_timeout=30).run()
        clean(backup)
        button(backup,'Préparer une sauvegarde complète').click().run()
        clean(backup)
        assert backup.session_state['backup_prepared']['files']==1
        button(backup,'J’ai téléchargé et conservé cette copie').click().run()
        clean(backup)
        assert service.backup_status()['confirmed']
        seller=db.authenticate('seller','test-password')
        sys.modules.pop('session_guard', None)
        locked=AppTest.from_file('iphone_app.py',default_timeout=30)
        for k,v in dict(mobile_user=seller,_auth_nonce='seller-test',_auth_seen=time.monotonic(),_auth_timeout=300,_auth_locked=False,mobile_page='Archives factures').items():
            locked.session_state[k]=v
        locked.run()
        clean(locked)
        assert locked.session_state['mobile_page']=='Caisse'
        button(locked,'Verrouiller maintenant').click().run()
        clean(locked)
        assert 'mobile_user' not in locked.session_state
        import session_guard
        state={'mobile_user':user,'_auth_seen':100,'_auth_timeout':60}
        with patch.object(session_guard,'st',SimpleNamespace(session_state=state)), patch.object(session_guard.time,'monotonic',return_value=161):
            session_guard._activity()
            assert state['_auth_locked']
            session_guard.gate()
            assert state=={'_lock_notice':True}
        gc.collect()
    print('PASS: full login, new screens, seller authorization, idle expiry, manual lock, invoice A5, WhatsApp confirmation and backups')

if __name__=='__main__':
    run()
