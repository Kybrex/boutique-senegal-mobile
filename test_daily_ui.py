from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date
import gc
from streamlit.testing.v1 import AppTest
import db

def check(at):
    assert not at.exception,[e.message for e in at.exception]
    assert not at.error,[e.value for e in at.error]
def button(at,label): return next(b for b in at.button if b.label==label)
def run():
    with TemporaryDirectory() as folder:
        db.DB_PATH=Path(folder)/'ui.db'; db.init_db()
        db.create_user('admin','Admin','test-password','admin')
        db.create_seller_with_user('Seller','','','seller','test-password')
        db.add_client('Awa','771234567','','')
        db.add_client('Client libre','','','')
        db.add_supplier('Fournisseur libre','','','','')
        db.add_product('Riz','Epicerie',500,1000,20,5,None)
        db.save_sale([{'id':1,'quantity':2,'sale_price':1000}],1,1,500,'Especes',0,date.today())
        at=AppTest.from_file('iphone_app.py',default_timeout=30).run(); check(at)
        next(w for w in at.text_input if w.label=="Nom d'utilisateur").set_value('admin')
        next(w for w in at.text_input if w.label=='Mot de passe').set_value('test-password')
        button(at,'Se connecter').click().run(); check(at)
        at.session_state['mobile_page']='Journal ventes'; at.run(); check(at)
        assert any(h.value=='Journal des ventes' for h in at.header)
        button(at,'Clients').click().run(); check(at)
        next(w for w in at.selectbox if w.label=='Client à supprimer').set_value('Client libre').run(); check(at)
        next(w for w in at.checkbox if w.label=='Je confirme la suppression de Client libre').check().run(); check(at)
        button(at,'Supprimer le client').click().run(); check(at)
        assert 'Client libre' not in list(db.clients().Client)
        button(at,'Fournisseurs').click().run(); check(at)
        next(w for w in at.checkbox if w.label=='Je confirme la suppression de Fournisseur libre').check().run(); check(at)
        button(at,'Supprimer le fournisseur').click().run(); check(at)
        assert db.suppliers().empty
        button(at,'Stock').click().run(); check(at)
        button(at,'Inventaire').click().run(); check(at)
        assert at.session_state['mobile_page']=='Inventaire'
        assert any(h.value=='Inventaire physique' for h in at.header)
        button(at,'Produits et quantités').click().run(); check(at)
        assert any(h.value=='Produits et stock' for h in at.header)
        next(w for w in at.number_input if w.label=='Quantité').set_value(17)
        button(at,'Enregistrer le stock').click().run(); check(at)
        assert any('18 → 17' in s for s in db.audit_logs().Details)
        next(w for w in at.number_input if w.label=="Nouveau prix de vente (FCFA)").set_value(1200)
        button(at,'Enregistrer les prix').click().run(); check(at)
        assert float(db.products().iloc[0].Vente)==1200
        assert any('1000.0 → 1200.0' in s for s in db.audit_logs().Details)
        for route,title in [('Clôture','Caisse journalière'),('Paiements','Encaissements et décaissements'),('Relances','Relances clients'),('Retours V3','Retours, échanges et remboursements'),('Inventaire','Inventaire physique'),('Réapprovisionnement','Alertes et réapprovisionnement'),('Bénéfice','Bénéfice de la boutique'),('Impression',"Centre d'impression")]:
            at.session_state['mobile_page']=route; at.run(); check(at)
            assert any(h.value==title for h in at.header),(route,[h.value for h in at.header])
        at.session_state['mobile_page']='Clôture'; at.run(); check(at)
        next(w for w in at.number_input if w.label=='Fonds initial en espèces').set_value(1000)
        button(at,'Ouvrir la caisse').click().run(); check(at)
        assert not any(b.label=='Ouvrir la caisse' for b in at.button)
        next(w for w in at.number_input if w.label=='Espèces réellement comptées').set_value(1500)
        button(at,'Clôturer la journée').click().run(); check(at)
        assert any('Clôture enregistrée' in s.value for s in at.success)
        at.session_state['mobile_page']='Relances'; at.run(); check(at)
        assert not any(e.label=='Ouvrir WhatsApp' for e in at.get('link_button'))
        next(w for w in at.checkbox if 'destinataire' in w.label).check().run(); check(at)
        assert any(e.label=='Ouvrir WhatsApp' for e in at.get('link_button'))
        at.session_state['mobile_user']={'id':2,'role':'seller','seller_id':1,'display_name':'Seller','username':'seller'}
        at.session_state['mobile_page']='Clôture'; at.run(); check(at)
        assert at.session_state['mobile_page']=='Caisse'
        gc.collect()
    print('PASS: eight menu routes, daily opening/closing, WhatsApp confirmation and seller access restrictions')
if __name__=='__main__': run()
