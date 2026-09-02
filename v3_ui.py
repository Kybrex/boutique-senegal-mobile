"""Écrans mobiles Boutique Senegal V3."""
from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import quote

import streamlit as st

import db
import v3_db as v3
from business_pdf import make_business_document_pdf, make_product_list_pdf
from offline_pos import make_offline_pos


def fcfa(value): return f"{float(value):,.0f} FCFA".replace(","," ")


def migration_required() -> bool:
    if v3.v3_ready(): return False
    st.error("La migration Supabase V3 doit être installée avant d'utiliser ce module.")
    error=v3.v3_error()
    if error: st.warning(f"Diagnostic Supabase : {error}")
    sql=(Path(__file__).parent/"supabase_schema.sql").read_text(encoding="utf-8")
    st.download_button("Télécharger la migration V3",sql,file_name="boutique_senegal_v3.sql",mime="text/sql")
    with st.expander("Afficher le code SQL à copier"): st.code(sql,language="sql")
    return True


def product_list_download(products=None) -> None:
    products=db.products() if products is None else products
    if products.empty: return
    pdf=make_product_list_pdf(products,db.get_settings())
    st.download_button("Imprimer la liste des produits",pdf,file_name=f"liste_produits_{date.today():%Y-%m-%d}.pdf",mime="application/pdf",icon=":material/picture_as_pdf:",width="stretch")


def documents_page(user):
    if migration_required(): return
    st.header("Devis, factures et livraisons",icon=":material/description:")
    st.session_state.setdefault("document_cart",[])
    products=db.products(); clients=db.clients()
    if products.empty: st.info("Ajoutez d'abord des produits."); return
    with st.expander("Nouveau document",expanded=not st.session_state.document_cart):
        product_map={r.Produit:r for _,r in products.iterrows()}
        with st.form("document_add_line"):
            name=st.selectbox("Produit",list(product_map)); row=product_map[name]
            quantity=st.number_input("Quantité",min_value=1,value=1,step=1); price=st.number_input("Prix unitaire",min_value=0.0,value=float(row.Vente),step=100.0)
            if st.form_submit_button("Ajouter la ligne"):
                st.session_state.document_cart.append({"product_id":int(row.id),"Produit":name,"quantity":int(quantity),"unit_price":float(price)}); st.rerun()
        if st.session_state.document_cart:
            st.dataframe(st.session_state.document_cart,hide_index=True,width="stretch")
            client_map={"Comptant":None}|dict(zip(clients.Client,clients.id))
            with st.form("create_document"):
                kind=st.selectbox("Type",["DEVIS","FACTURE","BON_LIVRAISON"],format_func=lambda x:{"DEVIS":"Devis","FACTURE":"Facture","BON_LIVRAISON":"Bon de livraison"}[x])
                client_name=st.selectbox("Client",list(client_map)); valid=st.date_input("Valable jusqu'au",value=date.today()+timedelta(days=15)); notes=st.text_area("Notes")
                if st.form_submit_button("Créer le document",type="primary"):
                    doc_id=v3.create_document(kind,client_map[client_name],valid if kind=="DEVIS" else None,notes,st.session_state.document_cart,int(user["id"])); db.log_action(int(user["id"]),"DOCUMENT_CREE",f"{kind} #{doc_id}"); st.session_state.document_cart=[]; st.success(f"Document #{doc_id} créé."); st.rerun()
            if st.button("Vider les lignes"): st.session_state.document_cart=[]; st.rerun()
    history=v3.documents(); st.subheader("Documents enregistrés"); st.dataframe(history,hide_index=True,width="stretch")
    if not history.empty:
        labels={f"{r.Type} #{int(r.id)} - {r.Client} - {fcfa(r.Total)}":int(r.id) for _,r in history.iterrows()}; selected=st.selectbox("Ouvrir un document",list(labels)); doc_id=labels[selected]
        document,items=v3.document_details(doc_id); pdf=make_business_document_pdf(document,items,db.get_settings())
        st.dataframe(items,hide_index=True,width="stretch"); st.download_button("Télécharger le PDF",pdf,file_name=f"document_{doc_id}.pdf",mime="application/pdf",icon=":material/picture_as_pdf:")
        cols=st.columns(2)
        if cols[0].button("Convertir en vente",type="primary"):
            st.session_state.mobile_cart=v3.document_cart(doc_id); st.session_state.mobile_page="Caisse"; v3.set_document_status(doc_id,"CONVERTI"); st.rerun()
        if cols[1].button("Marquer envoyé"): v3.set_document_status(doc_id,"ENVOYÉ"); st.rerun()


def purchase_orders_page(user):
    if migration_required(): return
    st.header("Commandes fournisseurs",icon=":material/inventory:")
    st.session_state.setdefault("purchase_cart",[]); products=db.products(); suppliers=db.suppliers()
    if products.empty or suppliers.empty: st.info("Ajoutez au moins un produit et un fournisseur."); return
    with st.expander("Nouvelle commande"):
        pmap={r.Produit:r for _,r in products.iterrows()}
        with st.form("purchase_order_line"):
            name=st.selectbox("Produit",list(pmap)); row=pmap[name]; qty=st.number_input("Quantité commandée",min_value=1,step=1); cost=st.number_input("Coût unitaire",min_value=0.0,value=float(row.Achat or 0),step=100.0)
            if st.form_submit_button("Ajouter"):
                st.session_state.purchase_cart.append({"product_id":int(row.id),"Produit":name,"quantity":int(qty),"unit_cost":float(cost)}); st.rerun()
        if st.session_state.purchase_cart:
            st.dataframe(st.session_state.purchase_cart,hide_index=True,width="stretch"); smap=dict(zip(suppliers.Fournisseur,suppliers.id))
            with st.form("purchase_order_create"):
                supplier=st.selectbox("Fournisseur",list(smap)); expected=st.date_input("Livraison prévue",value=date.today()+timedelta(days=7)); notes=st.text_input("Observation")
                if st.form_submit_button("Créer le bon de commande",type="primary"):
                    oid=v3.create_purchase_order(int(smap[supplier]),expected,notes,st.session_state.purchase_cart,int(user["id"])); st.session_state.purchase_cart=[]; db.log_action(int(user["id"]),"COMMANDE_FOURNISSEUR",f"Commande #{oid}"); st.success(f"Commande #{oid} créée."); st.rerun()
    orders=v3.purchase_orders(); st.dataframe(orders,hide_index=True,width="stretch")
    if not orders.empty:
        labels={f"Commande #{int(r.id)} - {r.Fournisseur} - {r.Statut}":int(r.id) for _,r in orders.iterrows()}; label=st.selectbox("Gérer une commande",list(labels)); oid=labels[label]; items=v3.purchase_order_details(oid); st.dataframe(items,hide_index=True,width="stretch")
        pending=items[items.Restante>0]
        if not pending.empty:
            imap={f"{r.Produit} - reste {int(r.Restante)}":r for _,r in pending.iterrows()}
            with st.form("receive_order"):
                ilabel=st.selectbox("Article reçu",list(imap)); item=imap[ilabel]; qty=st.number_input("Quantité reçue",min_value=1,max_value=int(item.Restante),step=1)
                if st.form_submit_button("Réceptionner et augmenter le stock",type="primary"): v3.receive_purchase_order_item(oid,int(item.id),int(qty)); db.log_action(int(user["id"]),"RECEPTION_COMMANDE",f"Commande #{oid} - {qty}"); st.success("Réception enregistrée."); st.rerun()
        order=orders[orders.id==oid].iloc[0]
        pdf_items=items.rename(columns={"Commande":"Quantite","Cout":"Prix"}); order_pdf=make_business_document_pdf({"id":oid,"Type":"BON_COMMANDE","Client":order.Fournisseur,"Total":order.Total,"Date":order.Date},pdf_items,db.get_settings())
        st.download_button("Télécharger le bon de commande PDF",order_pdf,file_name=f"bon_commande_{oid}.pdf",mime="application/pdf",icon=":material/picture_as_pdf:")
        if float(order.Reste)>0:
            with st.form("supplier_payment"):
                amount=st.number_input("Paiement fournisseur",min_value=1.0,max_value=float(order.Reste),step=100.0); method=st.selectbox("Mode",["Especes","Wave","Orange Money","Virement","Carte"])
                if st.form_submit_button("Enregistrer le règlement"): v3.add_supplier_payment(oid,amount,method,int(user["id"])); st.success("Règlement enregistré."); st.rerun()


def returns_page(user):
    if migration_required(): return
    st.header("Retours, échanges et remboursements",icon=":material/assignment_return:")
    sales=db.report(date(2000,1,1),date.today())
    if sales.empty: st.info("Aucune vente disponible."); return
    labels={f"Ticket #{int(r.Ticket)} - {r.Client} - {fcfa(r.Total)}":int(r.Ticket) for _,r in sales.iterrows()}; label=st.selectbox("Vente",list(labels)); sale_id=labels[label]; details=db.sale_details(sale_id)
    if details is None: return
    _,items=details; st.dataframe(items,hide_index=True,width="stretch")
    if items.empty: return
    imap={f"{r.Produit} - vendu {int(r.Quantite)}":r for _,r in items.iterrows()}
    with st.form("advanced_return"):
        ilabel=st.selectbox("Produit retourné",list(imap)); item=imap[ilabel]; qty=st.number_input("Quantité",min_value=1,max_value=int(item.Quantite),step=1); reason=st.text_input("Motif du retour"); resolution=st.selectbox("Solution",["REMBOURSEMENT","AVOIR","ECHANGE"],format_func=lambda x:{"REMBOURSEMENT":"Remboursement","AVOIR":"Avoir client","ECHANGE":"Échange"}[x]); method=st.selectbox("Mode de remboursement",["Especes","Wave","Orange Money","Carte"])
        approval_pin=st.text_input("PIN administrateur requis",type="password",max_chars=4) if user.get("role")=="seller" else ""
        if st.form_submit_button("Valider le retour",type="primary"):
            approved=True
            if user.get("role")=="seller":
                try:
                    import v4_db as v4
                    approved=v4.v4_ready() and v4.verify_admin_pin(approval_pin,int(user["id"]),"RETOUR_VENDEUR",0,f"Ticket #{sale_id}")
                except Exception: approved=False
            if not approved: st.error("PIN administrateur incorrect.")
            else:
                refund=v3.process_return(sale_id,int(item.product_id),int(qty),reason,resolution,method,int(user["id"])); db.log_action(int(user["id"]),"RETOUR_AVANCE",f"Ticket #{sale_id} - {resolution} - {refund}"); st.success(f"Retour enregistré. Montant : {fcfa(refund)}"); st.rerun()
    st.subheader("Historique"); st.dataframe(v3.returns_history(),hide_index=True,width="stretch")


def cash_movements_section(user,day):
    if not v3.v3_ready(): return
    st.subheader("Mouvements de caisse")
    with st.form("cash_movement"):
        movement=st.selectbox("Type",["FOND_INITIAL","ENTREE","SORTIE"],format_func=lambda x:{"FOND_INITIAL":"Fonds initial","ENTREE":"Entrée","SORTIE":"Sortie"}[x]); amount=st.number_input("Montant du mouvement",min_value=1.0,step=500.0); label=st.text_input("Motif")
        if st.form_submit_button("Enregistrer le mouvement"): v3.add_cash_movement(day,movement,amount,label,int(user["id"])); db.log_action(int(user["id"]),"MOUVEMENT_CAISSE",f"{movement} {amount}"); st.success("Mouvement enregistré."); st.rerun()
    moves=v3.cash_movements(day); st.dataframe(moves,hide_index=True,width="stretch"); st.metric("Ajustement de caisse",fcfa(v3.cash_adjustment(day)))


def loyalty_page(user):
    if migration_required(): return
    st.header("Fidélité clients",icon=":material/loyalty:")
    customers=v3.loyalty_customers(); st.dataframe(customers,hide_index=True,width="stretch")
    if customers.empty: return
    cmap={f"{r.Client} - {int(r.Points)} points - avoir {fcfa(r.Avoir)}":int(r.id) for _,r in customers.iterrows()}
    with st.form("loyalty_adjust"):
        label=st.selectbox("Client",list(cmap)); points=st.number_input("Ajouter/retirer des points",value=0,step=1); credit=st.number_input("Ajouter/retirer un avoir (FCFA)",value=0.0,step=100.0)
        if st.form_submit_button("Mettre à jour"): v3.adjust_loyalty(cmap[label],int(points),float(credit)); db.log_action(int(user["id"]),"FIDELITE_MODIFIEE",label); st.success("Compte fidélité mis à jour."); st.rerun()
    st.caption("Les ventes enregistrées rapportent automatiquement 1 point par tranche de 1 000 FCFA encaissés.")


def permissions_page(user):
    if migration_required(): return
    st.header("Permissions des vendeurs",icon=":material/admin_panel_settings:")
    accounts=v3.permissions(); st.dataframe(accounts,hide_index=True,width="stretch")
    if accounts.empty: st.info("Aucun compte vendeur."); return
    labels={f"{r.Nom} ({r.Identifiant})":r for _,r in accounts.iterrows()}; label=st.selectbox("Vendeur",list(labels)); row=labels[label]
    with st.form("seller_permissions"):
        stock=st.checkbox("Voir le stock",value=bool(row.Stock)); discount=st.checkbox("Accorder des remises",value=bool(row.Remises)); returns=st.checkbox("Gérer les retours",value=bool(row.Retours)); credit=st.checkbox("Faire des ventes à crédit",value=bool(row.Credits))
        if st.form_submit_button("Enregistrer les permissions",type="primary"): v3.update_permissions(int(row.id),stock,discount,returns,credit); db.log_action(int(user["id"]),"PERMISSIONS_MODIFIEES",label); st.success("Permissions enregistrées."); st.rerun()


def lots_page(user):
    if migration_required(): return
    st.header("Lots et dates d'expiration",icon=":material/event_busy:")
    alerts=v3.expiry_alerts();
    if alerts.empty: st.success("Aucun lot n'expire dans les 30 prochains jours.")
    else: st.warning(f"{len(alerts)} lot(s) à surveiller."); st.dataframe(alerts,hide_index=True,width="stretch")
    products=db.products()
    if not products.empty:
        pmap=dict(zip(products.Produit,products.id))
        with st.form("new_lot"):
            product=st.selectbox("Produit",list(pmap)); batch=st.text_input("Numéro du lot"); expiry=st.date_input("Date d'expiration",value=date.today()+timedelta(days=180)); quantity=st.number_input("Quantité du lot",min_value=0,step=1); notes=st.text_input("Observation")
            if st.form_submit_button("Ajouter le lot",type="primary"):
                try: v3.add_lot(int(pmap[product]),batch,expiry,int(quantity),notes); db.log_action(int(user["id"]),"LOT_AJOUTE",f"{product} - {batch}"); st.success("Lot ajouté."); st.rerun()
                except Exception as error: st.error(str(error))
    st.dataframe(v3.lots(),hide_index=True,width="stretch")


def offline_page(user):
    if migration_required(): return
    st.header("Caisse de secours hors connexion",icon=":material/cloud_off:")
    st.info("Téléchargez cette caisse avant une coupure. Les ventes restent sur l'appareil puis sont exportées en JSON pour synchronisation.")
    products=db.products(); settings=db.get_settings(); html=make_offline_pos(products,str(settings.get("shop_name","Boutique Senegal")))
    st.download_button("Télécharger la caisse hors connexion",html,file_name="caisse_hors_connexion.html",mime="text/html",icon=":material/download:",width="stretch")
    uploaded=st.file_uploader("Importer les ventes hors connexion",type=["json"])
    sellers=db.sellers()
    if uploaded is not None and not sellers.empty:
        try: bundle=json.loads(uploaded.getvalue().decode("utf-8")); smap=dict(zip(sellers.Vendeur,sellers.id)); seller=st.selectbox("Vendeur associé",list(smap))
        except Exception: bundle=None; st.error("Fichier JSON invalide.")
        if bundle and st.button("Synchroniser les ventes",type="primary"):
            result=v3.sync_offline_sales(bundle,int(smap[seller]),int(user["id"])); st.success(f"{result['imported']} vente(s) importée(s), {result['skipped']} déjà présente(s).");
            if result["errors"]: st.warning("Certaines ventes n'ont pas été importées : " + " | ".join(result["errors"][:5]))


def stock_readonly_page():
    st.header("Consultation du stock",icon=":material/inventory_2:"); products=db.products(); columns=[c for c in ["Produit","Categorie","Vente","Stock","Minimum","Code_barres","Photo"] if c in products.columns]; st.dataframe(products[columns],hide_index=True,width="stretch",column_config={"Photo":st.column_config.ImageColumn("Photo")})


def credit_reminder_link(row) -> str:
    digits="".join(c for c in str(row.Telephone) if c.isdigit()); status=str(row.Statut).replace("_"," ").lower()
    message=quote(f"Bonjour {row.Client}, rappel Boutique Senegal : le solde du ticket #{int(row.Ticket)} est de {fcfa(row.Reste)}. Échéance : {row.Echeance} ({status}). Merci.")
    return f"https://wa.me/{digits}?text={message}" if digits else f"https://wa.me/?text={message}"
