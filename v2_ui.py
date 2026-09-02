"""Écrans administrateur Boutique Senegal V2."""
from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import streamlit as st

import db


def fcfa(value: float) -> str:
    return f"{value:,.0f} FCFA".replace(",", " ")


def migration_required() -> bool:
    if db.v2_ready():
        return False
    st.error("La migration Supabase V2 doit être installée avant d'utiliser ce module.")
    st.info("Dans Supabase → SQL Editor, exécutez le fichier supabase_schema.sql mis à jour, puis redémarrez l'application.")
    error = db.v2_error()
    if error:
        st.warning(f"Diagnostic Supabase : {error}")
    sql = (Path(__file__).parent / "supabase_schema.sql").read_text(encoding="utf-8")
    st.download_button("Télécharger la migration V2", sql, file_name="boutique_senegal_v2.sql", mime="text/sql")
    with st.expander("Afficher le code SQL à copier"):
        st.code(sql, language="sql")
    return True


def decode_barcode(upload) -> str:
    if upload is None:
        return ""
    try:
        import zxingcpp
        from PIL import Image
        image = Image.open(upload)
        results = zxingcpp.read_barcodes(image)
        return results[0].text if results else ""
    except Exception:
        return ""


def dashboard_page() -> None:
    if migration_required(): return
    st.header("Tableau de bord V2", icon=":material/monitoring:")
    period = st.segmented_control("Période", ["Aujourd'hui", "7 jours", "30 jours"], default="Aujourd'hui")
    days = {"Aujourd'hui": 0, "7 jours": 6, "30 jours": 29}[period]
    end = date.today(); start = end - timedelta(days=days); data = db.dashboard(start, end)
    col1, col2 = st.columns(2)
    col1.metric("Chiffre d'affaires", fcfa(data["sales"])); col2.metric("Bénéfice brut", fcfa(data["gross_profit"]))
    col1.metric("Dépenses", fcfa(data["expenses"])); col2.metric("Solde", fcfa(data["net"]))
    col1.metric("Transactions", data["transactions"]); col2.metric("Créances clients", fcfa(data["debt"]))
    performance = data["performance"]
    if not performance.empty:
        st.subheader("Meilleures ventes")
        st.bar_chart(performance.set_index("Produit")["Chiffre"])
        st.dataframe(performance, hide_index=True, width="stretch")
    sales = db.report(start, end)
    if not sales.empty:
        sellers = sales.groupby("Vendeur", as_index=False).agg(Ventes=("Total", "sum"), Tickets=("Ticket", "count")).sort_values("Ventes", ascending=False)
        st.subheader("Performance des vendeurs")
        st.bar_chart(sellers.set_index("Vendeur")["Ventes"])
        st.dataframe(sellers, hide_index=True, width="stretch")
    st.subheader("Alertes et réapprovisionnement")
    alerts = db.low_stock()
    if alerts.empty: st.success("Aucune rupture ni alerte de stock.")
    else:
        alerts = alerts.copy(); alerts["A_commander"] = (alerts.Minimum * 2 - alerts.Stock).clip(lower=0)
        st.dataframe(alerts, hide_index=True, width="stretch")


def cash_page(user: dict) -> None:
    if migration_required(): return
    st.header("Clôture de caisse", icon=":material/point_of_sale:")
    day = st.date_input("Journée", value=date.today())
    sellers = db.sellers(); seller_map = {"Tous les vendeurs": None} | dict(zip(sellers.Vendeur, sellers.id))
    seller_name = st.selectbox("Vendeur", list(seller_map)); seller_id = seller_map[seller_name]
    summary = db.cash_summary(day, None if seller_id is None else int(seller_id))
    st.dataframe(summary, hide_index=True, width="stretch")
    expected = float(summary.loc[summary.Paiement == "Especes", "Montant"].sum()) if not summary.empty else 0.0
    st.metric("Espèces attendues", fcfa(expected))
    with st.form("cash_closing"):
        counted = st.number_input("Espèces réellement comptées", min_value=0.0, step=500.0)
        notes = st.text_area("Observations")
        if st.form_submit_button("Clôturer la caisse", type="primary"):
            db.close_cash(day, None if seller_id is None else int(seller_id), counted, notes, int(user["id"]))
            db.log_action(int(user["id"]), "CLOTURE_CAISSE", f"{day} - {seller_name} - écart {counted-expected}")
            st.success(f"Caisse clôturée. Écart : {fcfa(counted-expected)}"); st.rerun()
    st.subheader("Historique des clôtures"); st.dataframe(db.cash_closings(), hide_index=True, width="stretch")


def security_page(user: dict) -> None:
    if migration_required(): return
    st.header("Sécurité et contrôle", icon=":material/security:")
    accounts = db.all_users(); st.dataframe(accounts, hide_index=True, width="stretch")
    sellers = accounts[accounts.Role == "seller"] if not accounts.empty else accounts
    if not sellers.empty:
        labels = {f"{r.Nom} ({r.Identifiant})": int(r.id) for _, r in sellers.iterrows()}
        selected = st.selectbox("Compte vendeur", list(labels)); selected_id = labels[selected]
        active = bool(sellers.loc[sellers.id == selected_id, "Actif"].iloc[0])
        col1, col2 = st.columns(2)
        if col1.button("Désactiver" if active else "Réactiver", type="primary"):
            db.set_user_active(selected_id, not active); db.log_action(int(user["id"]), "COMPTE_MODIFIE", selected); st.rerun()
        with st.form("reset_password"):
            password = st.text_input("Nouveau mot de passe", type="password")
            confirm = st.text_input("Confirmer", type="password")
            if st.form_submit_button("Réinitialiser le mot de passe"):
                if len(password) < 8: st.error("Le mot de passe doit contenir au moins 8 caractères.")
                elif password != confirm: st.error("Les mots de passe ne correspondent pas.")
                else:
                    db.reset_user_password(selected_id, password); db.log_action(int(user["id"]), "MOT_DE_PASSE_REINITIALISE", selected); st.success("Mot de passe mis à jour.")
    st.subheader("Journal d'activité"); st.dataframe(db.audit_logs(), hide_index=True, width="stretch")


def inventory_page(user: dict) -> None:
    if migration_required(): return
    st.header("Inventaire physique", icon=":material/fact_check:")
    stock = db.inventory_snapshot()
    if stock.empty: st.info("Ajoutez d'abord des produits."); return
    choices = {f"{r.Produit} — stock système: {int(r.Stock)}": r for _, r in stock.iterrows()}
    selected = st.selectbox("Produit compté", list(choices)); row = choices[selected]
    with st.form("inventory_count"):
        counted = st.number_input("Quantité réellement comptée", min_value=0, value=int(row.Stock), step=1)
        notes = st.text_input("Observation")
        if st.form_submit_button("Valider et corriger le stock", type="primary"):
            db.save_inventory_count(int(row.id), int(counted), int(user["id"]), notes)
            db.log_action(int(user["id"]), "INVENTAIRE", f"{row.Produit}: {row.Stock} → {counted}")
            st.success("Inventaire enregistré et stock corrigé."); st.rerun()
    st.subheader("Historique des écarts"); st.dataframe(db.inventory_history(), hide_index=True, width="stretch")


def stores_page(user: dict) -> None:
    if migration_required(): return
    st.header("Gestion des boutiques", icon=":material/store:")
    with st.expander("Ajouter une boutique"):
        with st.form("new_store"):
            name=st.text_input("Nom"); address=st.text_input("Adresse"); phone=st.text_input("Téléphone")
            if st.form_submit_button("Ajouter", type="primary"):
                if not name.strip(): st.error("Le nom est obligatoire.")
                else: db.add_store(name,address,phone); st.success("Boutique ajoutée."); st.rerun()
    shops=db.stores(); st.dataframe(shops,hide_index=True,width="stretch")
    products=db.products()
    if len(shops) >= 2 and not products.empty:
        shop_map=dict(zip(shops.Boutique,shops.id)); product_map=dict(zip(products.Produit,products.id))
        with st.form("stock_transfer"):
            product=st.selectbox("Produit",list(product_map)); source=st.selectbox("Boutique source",list(shop_map)); destination=st.selectbox("Boutique destination",list(shop_map),index=1)
            quantity=st.number_input("Quantité",min_value=1,step=1); notes=st.text_input("Observation")
            if st.form_submit_button("Transférer le stock",type="primary"):
                try:
                    db.transfer_stock(int(product_map[product]),int(shop_map[source]),int(shop_map[destination]),int(quantity),int(user["id"]),notes)
                    db.log_action(int(user["id"]),"TRANSFERT_STOCK",f"{product}: {source} → {destination}, {quantity}"); st.success("Transfert enregistré."); st.rerun()
                except ValueError as error: st.error(str(error))
    st.subheader("Historique des transferts"); st.dataframe(db.transfer_history(),hide_index=True,width="stretch")
    if not shops.empty:
        selected_shop=st.selectbox("Voir le stock d'une boutique",shops.Boutique.tolist()); selected_id=int(shops.loc[shops.Boutique==selected_shop,"id"].iloc[0])
        st.dataframe(db.store_inventory(selected_id),hide_index=True,width="stretch")


def settings_page(user: dict) -> None:
    if migration_required(): return
    st.header("Paramètres et sauvegardes", icon=":material/settings:")
    settings=db.get_settings()
    with st.form("shop_settings"):
        name=st.text_input("Nom de la boutique",value=str(settings.get("shop_name", "Boutique Senegal")))
        phone=st.text_input("Téléphone",value=str(settings.get("phone", ""))); address=st.text_input("Adresse",value=str(settings.get("address", "")))
        logo=st.text_input("Lien du logo",value=str(settings.get("logo_url", ""))); footer=st.text_input("Message sur le ticket",value=str(settings.get("receipt_footer", "Merci pour votre achat !")))
        if st.form_submit_button("Enregistrer",type="primary"):
            db.update_settings(name,phone,address,logo,footer); db.log_action(int(user["id"]),"PARAMETRES_MODIFIES",name); st.success("Paramètres enregistrés."); st.rerun()
    st.subheader("Sauvegarde complète")
    if st.button("Préparer la sauvegarde"):
        files={"produits.csv":db.products(),"clients.csv":db.clients(),"fournisseurs.csv":db.suppliers(),"utilisateurs.csv":db.all_users(),"ventes.csv":db.report(date(2000,1,1),date.today()),"depenses.csv":db.expenses(date(2000,1,1),date.today()),"inventaires.csv":db.inventory_history(),"transferts.csv":db.transfer_history(),"journal.csv":db.audit_logs()}
        output=BytesIO()
        with ZipFile(output,"w",ZIP_DEFLATED) as archive:
            for filename,frame in files.items(): archive.writestr(filename,frame.to_csv(index=False).encode("utf-8-sig"))
            archive.writestr("supabase_schema.sql","Utilisez le fichier supabase_schema.sql du dépôt GitHub pour restaurer la structure.")
        st.download_button("Télécharger la sauvegarde ZIP",output.getvalue(),file_name=f"boutique_senegal_{date.today()}.zip",mime="application/zip")


def whatsapp_receipt_link(phone: str, ticket: int, total: float) -> str:
    digits="".join(c for c in phone if c.isdigit())
    message=quote(f"Bonjour, voici votre reçu Boutique Senegal. Ticket #{ticket}, total {fcfa(total)}.")
    return f"https://wa.me/{digits}?text={message}" if digits else f"https://wa.me/?text={message}"
