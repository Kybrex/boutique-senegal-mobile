"""Écrans Boutique Senegal V4."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

import db
import v4_db as v4
from business_pdf import make_product_list_pdf
from v4_pdf import make_barcode_labels_pdf, make_catalog_pdf, make_statement_pdf


def fcfa(value) -> str: return f"{float(value or 0):,.0f} FCFA".replace(",", " ")


def migration_required() -> bool:
    if v4.v4_ready(): return False
    st.warning("La migration Supabase V4 doit être installée avant d'utiliser ce module.")
    error=v4.v4_error()
    if error: st.caption(f"Diagnostic Supabase : {error}")
    schema=(Path(__file__).parent/"supabase_schema.sql").read_bytes()
    st.download_button("Télécharger la migration V4",schema,file_name="supabase_schema.sql",mime="text/plain",icon=":material/download:")
    return True


def impression_page(user):
    st.header("Centre d'impression",icon=":material/print:")
    products=db.products(); settings=db.get_settings(); clients=db.clients(); suppliers=db.suppliers()
    product_tab,label_tab,client_tab,supplier_tab,catalog_tab=st.tabs(["Liste produits","Étiquettes","Relevé client","Relevé fournisseur","Catalogue"])
    with product_tab:
        st.caption("Liste complète du stock avec prix, code-barres et seuil minimum.")
        st.dataframe(products,hide_index=True,width="stretch")
        st.download_button("Imprimer la liste des produits",make_product_list_pdf(products,settings),file_name=f"liste_produits_{date.today()}.pdf",mime="application/pdf",icon=":material/print:",width="stretch")
    with label_tab:
        if products.empty: st.info("Aucun produit à imprimer.")
        else:
            categories=["Toutes"]+sorted(str(x) for x in products.Categorie.dropna().unique() if str(x))
            category=st.selectbox("Catégorie",categories,key="label_category"); selected=products if category=="Toutes" else products[products.Categorie.astype(str)==category]
            st.caption(f"{len(selected)} étiquette(s), 24 par page A4.")
            st.download_button("Imprimer les étiquettes code-barres",make_barcode_labels_pdf(selected,settings),file_name=f"etiquettes_{date.today()}.pdf",mime="application/pdf",icon=":material/barcode:",width="stretch")
    with client_tab:
        if clients.empty: st.info("Aucun client.")
        else:
            cmap={r.Client:r for _,r in clients.iterrows()}; name=st.selectbox("Client",list(cmap),key="statement_client"); row=cmap[name]; history=v4.client_statement(int(row.id)); st.dataframe(history,hide_index=True,width="stretch")
            st.download_button("Imprimer le relevé client",make_statement_pdf("Relevé client",row.to_dict(),history,settings),file_name=f"releve_client_{int(row.id)}.pdf",mime="application/pdf",icon=":material/print:",width="stretch")
    with supplier_tab:
        if suppliers.empty: st.info("Aucun fournisseur.")
        else:
            smap={r.Fournisseur:r for _,r in suppliers.iterrows()}; name=st.selectbox("Fournisseur",list(smap),key="statement_supplier"); row=smap[name]; history=v4.supplier_statement(int(row.id)); st.dataframe(history,hide_index=True,width="stretch")
            st.download_button("Imprimer le relevé fournisseur",make_statement_pdf("Relevé fournisseur",row.to_dict(),history,settings),file_name=f"releve_fournisseur_{int(row.id)}.pdf",mime="application/pdf",icon=":material/print:",width="stretch")
    with catalog_tab:
        available=products[products.Stock>0] if not products.empty else products; st.dataframe(available[[c for c in ["Produit","Categorie","Vente","Stock","Photo"] if c in available]],hide_index=True,width="stretch",column_config={"Photo":st.column_config.ImageColumn("Photo")})
        st.download_button("Imprimer le catalogue clients",make_catalog_pdf(available,settings),file_name=f"catalogue_{date.today()}.pdf",mime="application/pdf",icon=":material/menu_book:",width="stretch")


def search_page():
    st.header("Recherche globale",icon=":material/search:")
    term=st.text_input("Rechercher",placeholder="Nom, téléphone, code-barres, ticket, document…")
    if term and len(term.strip())<2: st.info("Saisissez au moins deux caractères.")
    results=v4.global_search(term) if len(term.strip())>=2 else {}
    if len(term.strip())>=2 and not results: st.warning("Aucun résultat.")
    for title,frame in results.items():
        with st.expander(f"{title} — {len(frame)} résultat(s)",expanded=True): st.dataframe(frame,hide_index=True,width="stretch")


def import_page(user):
    st.header("Importation Excel / CSV",icon=":material/upload_file:")
    st.info("L'import fusionne par nom : les lignes existantes sont mises à jour, les nouvelles sont ajoutées.")
    kind_label=st.segmented_control("Données",["Produits","Clients","Fournisseurs"],default="Produits")
    uploaded=st.file_uploader("Fichier .xlsx ou .csv",type=["xlsx","csv"])
    if uploaded is None:
        columns={"Produits":["Nom","Catégorie","Prix achat","Prix vente","Stock","Minimum","Code-barres"],"Clients":["Nom","Téléphone","Email","Adresse"],"Fournisseurs":["Nom","Contact","Téléphone","Email","Adresse"]}[kind_label]
        st.caption("Colonnes acceptées : "+", ".join(columns)); return
    try:
        frame=pd.read_excel(uploaded) if uploaded.name.lower().endswith(".xlsx") else pd.read_csv(uploaded,sep=None,engine="python")
    except Exception as error: st.error(f"Impossible de lire le fichier : {error}"); return
    st.dataframe(frame.head(100),hide_index=True,width="stretch"); st.caption(f"{len(frame)} ligne(s) détectée(s).")
    confirm=st.checkbox("Je confirme l'importation et la mise à jour des doublons")
    if st.button("Importer maintenant",type="primary",disabled=not confirm):
        try:
            key={"Produits":"products","Clients":"clients","Fournisseurs":"suppliers"}[kind_label]; result=v4.import_rows(key,frame.to_dict("records")); db.log_action(int(user["id"]),"IMPORT_V4",f"{kind_label}: {result}")
            st.success(f"Import terminé : {result['inserted']} ajout(s), {result['updated']} mise(s) à jour, {result['ignored']} ignorée(s).")
        except Exception as error: st.error(f"Import interrompu : {error}")


def variants_page(user):
    if migration_required(): return
    st.header("Variantes de produits",icon=":material/style:")
    st.caption("Gérez taille, couleur, modèle ou capacité avec un stock et un code-barres distincts.")
    products=db.products()
    if products.empty: st.info("Ajoutez d'abord un produit."); return
    pmap=dict(zip(products.Produit,products.id))
    with st.form("new_variant"):
        product=st.selectbox("Produit",list(pmap)); name=st.text_input("Variante",placeholder="Ex. Bleu / 256 Go / Taille M"); sku=st.text_input("Référence SKU"); barcode=st.text_input("Code-barres"); stock=st.number_input("Stock variante",min_value=0,step=1); adjustment=st.number_input("Ajustement du prix",value=0.0,step=100.0)
        if st.form_submit_button("Ajouter la variante",type="primary"):
            try: v4.add_variant(int(pmap[product]),name,sku,barcode,int(stock),adjustment); db.log_action(int(user["id"]),"VARIANTE_AJOUTEE",f"{product} - {name}"); st.success("Variante ajoutée."); st.rerun()
            except Exception as error: st.error(str(error))
    data=v4.variants(); st.dataframe(data,hide_index=True,width="stretch")
    if not data.empty:
        labels={f"{r.Produit} — {r.Variante}":r for _,r in data.iterrows()}; label=st.selectbox("Modifier le stock",list(labels)); row=labels[label]; new_stock=st.number_input("Nouveau stock",min_value=0,value=int(row.Stock),step=1)
        if st.button("Enregistrer le stock variante"):
            v4.update_variant_stock(int(row.id),int(new_stock)); st.success("Stock variante mis à jour."); st.rerun()


def commissions_page(user):
    if migration_required(): return
    st.header("Commissions vendeurs",icon=":material/percent:")
    rates=v4.commission_rates(); st.dataframe(rates,hide_index=True,width="stretch")
    if not rates.empty:
        labels={r.Vendeur:r for _,r in rates.iterrows()}; name=st.selectbox("Vendeur",list(labels)); row=labels[name]
        with st.form("commission_rate"):
            rate=st.number_input("Commission (%)",min_value=0.0,max_value=100.0,value=float(row.Taux),step=.5)
            if st.form_submit_button("Enregistrer",type="primary"): v4.set_commission_rate(int(row.id),rate); db.log_action(int(user["id"]),"TAUX_COMMISSION",f"{name}: {rate}%"); st.success("Taux enregistré."); st.rerun()
    period=st.date_input("Période des commissions",value=(date.today().replace(day=1),date.today()))
    if isinstance(period,(tuple,list)) and len(period)==2: st.dataframe(v4.commission_report(period[0],period[1]),hide_index=True,width="stretch")


def approvals_page(user):
    if migration_required(): return
    st.header("Approbations sensibles",icon=":material/password:")
    current=v4.approval_settings()
    st.caption("Le PIN administrateur est demandé au vendeur pour une remise importante. Les suppressions et modifications sensibles restent réservées à l'administrateur.")
    with st.form("approval_settings"):
        pin=st.text_input("Nouveau PIN administrateur (4 chiffres)",type="password",max_chars=4); threshold=st.number_input("Seuil de remise nécessitant le PIN (%)",min_value=0.0,max_value=100.0,value=float(current["threshold"]),step=1.0); backup_days=st.number_input("Sauvegarde automatique tous les (jours)",min_value=1,max_value=30,value=int(current["backup_days"]),step=1)
        if st.form_submit_button("Enregistrer",type="primary"):
            try: v4.set_admin_pin(pin,threshold,int(backup_days)); db.log_action(int(user["id"]),"SECURITE_V4","PIN et seuil actualisés"); st.success("Paramètres de sécurité enregistrés."); st.rerun()
            except ValueError as error: st.error(str(error))
    st.subheader("Affectation des vendeurs aux boutiques")
    assignments=v4.seller_store_assignments(); stores=db.stores()
    if assignments.empty or stores.empty: st.info("Ajoutez un vendeur et une boutique pour créer une affectation.")
    else:
        amap={f"{r.Vendeur} ({r.Identifiant})":r for _,r in assignments.iterrows()}; smap=dict(zip(stores.Boutique,stores.id)); label=st.selectbox("Compte vendeur",list(amap)); current=amap[label]; names=list(smap); current_name=current.Boutique if current.Boutique in names else names[0]; store=st.selectbox("Boutique de vente",names,index=names.index(current_name))
        if st.button("Affecter à la boutique"):
            v4.set_user_store(int(current.id),int(smap[store])); db.log_action(int(user["id"]),"AFFECTATION_BOUTIQUE",f"{label} → {store}"); st.success("Affectation enregistrée. Le vendeur doit se reconnecter."); st.rerun()


def automation_page(user):
    if migration_required(): return
    st.header("Alertes, prévisions et sauvegardes",icon=":material/notifications_active:")
    if st.button("Actualiser les alertes",type="primary"):
        st.session_state.v4_notifications=v4.refresh_notifications()
    alerts=st.session_state.get("v4_notifications")
    if alerts is None: alerts=v4.refresh_notifications()
    if alerts.empty: st.success("Aucune alerte active.")
    else: st.dataframe(alerts,hide_index=True,width="stretch")
    st.subheader("Prévisions de réapprovisionnement"); forecast=v4.reorder_forecast(); st.dataframe(forecast,hide_index=True,width="stretch")
    if not forecast.empty: st.download_button("Exporter les suggestions CSV",forecast.to_csv(index=False).encode("utf-8-sig"),file_name="previsions_reapprovisionnement.csv",mime="text/csv")
    st.subheader("Sauvegardes automatiques"); st.caption(f"État de cette session : {st.session_state.get('v4_backup_status','non vérifiée')}")
    if st.button("Vérifier et créer si l'échéance est atteinte"):
        status=v4.automatic_backup_if_due(); st.session_state.v4_backup_status=status; st.success(f"Sauvegarde : {status}")
    st.dataframe(v4.backup_history(),hide_index=True,width="stretch")
    st.info("Les alertes et sauvegardes sont actualisées à l'ouverture de l'application. Pour une exécution quand l'application est totalement fermée, utilisez un planificateur externe.")


def owner_page():
    if migration_required(): return
    st.header("Tableau de bord propriétaire",icon=":material/leaderboard:")
    period=st.date_input("Période",value=(date.today().replace(day=1),date.today()),key="owner_period")
    if not isinstance(period,(tuple,list)) or len(period)!=2: return
    data=v4.owner_dashboard(period[0],period[1])
    with st.container(border=True): st.metric("Chiffre d'affaires",fcfa(data["sales"])); st.metric("Tickets",data["tickets"]); st.metric("Créances totales",fcfa(data["debt"]))
    st.subheader("Comparaison des boutiques"); st.dataframe(data["stores"],hide_index=True,width="stretch")
    st.subheader("Comparaison des vendeurs"); st.dataframe(data["commissions"],hide_index=True,width="stretch")
    st.subheader("Produits à réapprovisionner"); st.dataframe(data["forecast"].head(20),hide_index=True,width="stretch")
