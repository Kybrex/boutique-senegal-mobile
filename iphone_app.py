"""Version mobile iPhone de Boutique Senegal.

Lancer avec : streamlit run iphone_app.py --server.port 8502
"""
from __future__ import annotations

from datetime import date, timedelta
import pandas as pd
import streamlit as st
from branding import LOGO_PATH

from receipt import make_receipt, make_receipt_pdf
import v2_ui
import daily_operations_ui as daily_ui


st.set_page_config(page_title="Boutique Sénégal", page_icon=":material/storefront:", layout="centered")


st.image(str(LOGO_PATH), width=220)


def validate_supabase_secrets() -> str | None:
    try:
        url = str(st.secrets.get("SUPABASE_URL", "")).strip()
        key = str(st.secrets.get("SUPABASE_KEY", "")).strip()
    except Exception:
        return None
    if not url and not key:
        return None
    if not url or not key:
        return "SUPABASE_URL et SUPABASE_KEY doivent être renseignés ensemble."
    if not url.startswith("https://") or ".supabase.co" not in url:
        return "SUPABASE_URL n'est pas une URL Supabase valide."
    try:
        key.encode("ascii")
    except UnicodeEncodeError:
        return "SUPABASE_KEY contient des accents ou caractères spéciaux. Remplacez le texte d'exemple par la vraie clé sb_secret_."
    if "nouvelle" in key.lower() or "votre" in key.lower() or len(key) < 30:
        return "SUPABASE_KEY est encore un texte d'exemple. Collez la vraie clé sb_secret_ créée dans Supabase."
    return None


secret_error = validate_supabase_secrets()
if secret_error:
    st.error("Configuration Supabase à corriger", icon=":material/key:")
    st.warning(secret_error)
    st.info("Ouvrez Manage app → Settings → Secrets, remplacez SUPABASE_KEY par la vraie clé secrète Supabase, puis redémarrez l'application.")
    st.stop()

import db
import v3_db as v3
import v3_ui
import v4_db as v4
import v4_ui
import business_features as features
import business_features_ui as features_ui
import workflow_service as workflows
import workflow_ui
import session_guard

db.init_db()
st.session_state.setdefault("mobile_cart", [])
st.session_state.setdefault("mobile_receipt", None)
st.session_state.setdefault("mobile_receipt_pdf", None)
st.session_state.setdefault("mobile_receipt_info", None)
st.session_state.setdefault("mobile_page", "Accueil")


def fcfa(value: float) -> str:
    return f"{value:,.0f} FCFA".replace(",", " ")


def sign_out() -> None:
    session_guard.clear_session()
    st.rerun()


if db.user_count() == 0:
    st.title("Boutique Senegal", icon=":material/storefront:")
    st.caption("Gestion de votre boutique")
    st.header("Administrateur principal", icon=":material/admin_panel_settings:")
    with st.form("mobile_setup_admin"):
        name = st.text_input("Nom complet")
        username = st.text_input("Nom d'utilisateur")
        password = st.text_input("Mot de passe", type="password")
        confirm = st.text_input("Confirmer le mot de passe", type="password")
        if st.form_submit_button("Créer l'administrateur", type="primary"):
            if len(name.strip()) < 2 or len(username.strip()) < 3 or len(password) < 8:
                st.error("Nom : 2 caractères ; identifiant : 3 ; mot de passe : 8.")
            elif password != confirm:
                st.error("Les mots de passe ne correspondent pas.")
            else:
                try:
                    db.create_user(username, name, password, "admin")
                    st.success("Administrateur créé. Connectez-vous.")
                except Exception:
                    st.error("Cet identifiant existe déjà.")
    st.stop()

session_guard.gate()
if "mobile_user" not in st.session_state:
    st.title("Boutique Senegal", icon=":material/storefront:")
    st.caption("Ventes, achats, stock et facturation")
    if st.session_state.get('_lock_notice'):
        st.info('Session verrouillée. Reconnectez-vous pour continuer.')
    with st.form("mobile_login"):
        # Browsers may override this hint for their saved-password manager.
        username = st.text_input("Nom d'utilisateur", autocomplete="off")
        password = st.text_input("Mot de passe", type="password", autocomplete="off")
        if st.form_submit_button("Se connecter", type="primary"):
            user = db.authenticate(username, password)
            if user:
                session_guard.clear_session()
                st.session_state.mobile_user = user
                session_guard.start(user, workflows.preferences()['idle_minutes']*60)
                st.session_state.mobile_page = "Accueil" if user["role"] == "admin" else "Caisse"
                try:
                    if db.v2_ready(): db.log_action(int(user["id"]), "CONNEXION", user["display_name"])
                except Exception:
                    pass
                st.rerun()
            st.error("Identifiant ou mot de passe incorrect.")
    st.stop()

user = st.session_state.mobile_user
session_guard.watch()
is_admin = user["role"] == "admin"
permissions = v3.user_permissions(user)
st.title("Boutique Senegal", icon=":material/storefront:")
st.caption(f"{user['display_name']} · {'Administrateur' if is_admin else 'Vendeur'}")

if is_admin and v4.v4_ready() and not st.session_state.get("v4_session_tasks_done"):
    try:
        st.session_state.v4_notifications=v4.refresh_notifications()
        st.session_state.v4_backup_status=v4.automatic_backup_if_due(user)
    except Exception as error:
        st.session_state.v4_backup_status=f"indisponible: {str(error)[:120]}"
    st.session_state.v4_session_tasks_done=True

# Seven everyday sections. Existing internal routes remain compatible with documents.
sections = {
    "Tableau de bord": [("Accueil", "Vue d'ensemble"), ("Rapports", "Rapports et dépenses"), ("Bénéfice", "Bénéfice")],
    "Ventes": [("Caisse", "Nouvelle vente"), ("Historique", "Historique"), ("Retours V3", "Retours et échanges"), ("Clôture", "Caisse journalière"), ("Paiements", "Paiements par mode")],
    "Achats": [("Achats", "Achat reçu"), ("Commandes", "Commandes et règlements"), ("Justificatifs", "Justificatifs")],
    "Stock": [("Produits", "Produits et quantités"), ("Inventaire", "Inventaire"), ("Réapprovisionnement", "À commander"), ("Impression", "Codes-barres et impressions")],
    "Fournisseurs": [("Fournisseurs", "Fournisseurs"), ("Dettes fournisseurs", "Sommes à payer")],
    "Clients": [("Clients", "Liste des clients"), ("Fiche client", "Fiche complète"), ("Crédits", "Historique et crédits"), ("Dettes clients", "Impayés et échéances"), ("Relances", "Relances WhatsApp")],
    "Facturation": [("Factures", "Factures des ventes"), ("Archives factures", "Factures émises"), ("Documents", "Devis et autres documents")],
}
if not is_admin:
    sections = {"Ventes": [("Caisse", "Nouvelle vente")]}
    if permissions["returns"] and v3.v3_ready():
        sections["Ventes"].append(("Retours V3", "Retours"))
    if permissions["stock"]:
        sections["Stock"] = [("Stock", "Stock disponible")]
settings_pages = [("Paramètres", "Boutique"), ("Comptes", "Vendeurs et comptes"),
                  ("Permissions", "Droits d'accès"), ("Sauvegardes", "Sauvegarder et récupérer"), ("Sécurité", "Sécurité des comptes")]
allowed = [route for routes in sections.values() for route, _ in routes]
if is_admin:
    allowed += [route for route, _ in settings_pages]
if st.session_state.mobile_page not in allowed:
    st.session_state.mobile_page = "Accueil" if is_admin else "Caisse"
current = st.session_state.mobile_page
active_section = next((name for name, routes in sections.items()
                       if current in [route for route, _ in routes]), "Réglages")
with st.sidebar:
    st.image(str(LOGO_PATH), width=180)
    st.header("Boutique Sénégal")
    for name, routes in sections.items():
        if st.button(name, key=f"simple_nav_{name}", width="stretch",
                     type="primary" if name == active_section else "secondary"):
            st.session_state.mobile_page = routes[0][0]
            st.rerun()
    if is_admin:
        with st.expander("Réglages"):
            for route, label in settings_pages:
                if st.button(label, key=f"simple_settings_{route}", width="stretch"):
                    st.session_state.mobile_page = route
                    st.rerun()
    st.button("Verrouiller maintenant", icon=":material/lock:", on_click=session_guard.manual_lock, width="stretch")
    st.caption(f"Verrouillage après {int(st.session_state.get('_auth_timeout',300)//60)} min sans activité.")
    st.button("Se déconnecter", icon=":material/logout:", on_click=sign_out, width="stretch")

if is_admin:
    features_ui.search_box()
st.subheader(active_section)
routes = settings_pages if active_section == "Réglages" else sections[active_section]
if len(routes) > 1:
    route_labels = dict(routes)
    route_names = list(route_labels)
    selected = st.radio("Afficher", route_names, index=route_names.index(current),
                        format_func=route_labels.get, horizontal=True,
                        key=f"simple_view_{active_section}_{current}", label_visibility="collapsed")
    if selected != current:
        st.session_state.mobile_page = selected
        st.rerun()
page = st.session_state.mobile_page

if page == "Bénéfice":
    features_ui.profit_page(user)
elif page == "Réapprovisionnement":
    if st.session_state.get("reorder_success"):
        st.success(st.session_state.pop("reorder_success"))
    features_ui.reorder_page(user)
elif page == "Dettes clients":
    features_ui.debts_page(user, "clients")
elif page == "Dettes fournisseurs":
    features_ui.debts_page(user, "fournisseurs")
elif page == "Sauvegardes":
    workflow_ui.backups_page(user)
elif page == "Archives factures":
    workflow_ui.archive_page(user)
elif page == "Justificatifs":
    workflow_ui.attachments_page(user)
elif page == "Fiche client":
    workflow_ui.client_page(user)
elif page == "Accueil":
    workflow_ui.backup_reminder(user)
    summary = db.today_summary().iloc[0]
    alerts = db.low_stock()
    st.header("Aujourd'hui", icon=":material/today:")
    with st.container(border=True):
        st.metric("Ventes", fcfa(float(summary.sales)))
        st.metric("Tickets", int(summary.transactions))
        st.metric("Alertes de stock", len(alerts))
    purchases = db.expenses(date.today(), date.today())
    purchase_total = float(purchases.loc[purchases.Libelle.str.startswith("Achat stock", na=False), "Montant"].sum()) if not purchases.empty else 0.0
    st.metric("Achats de stock aujourd'hui", fcfa(purchase_total))
    if st.button("Voir les impayés clients"):
        features_ui.go("Dettes clients")
    if st.button("Voir les sommes dues aux fournisseurs"):
        features_ui.go("Dettes fournisseurs")
    if st.button("Préparer les commandes de stock"):
        features_ui.go("Réapprovisionnement")
    st.subheader("Stock à surveiller", icon=":material/warning:")
    if alerts.empty:
        st.success("Aucune alerte de stock.")
    else:
        st.dataframe(alerts, hide_index=True)
    if db.v2_ready():
        credit_alerts = db.credit_alerts()
        st.subheader("Échéances de crédits", icon=":material/notifications_active:")
        if credit_alerts.empty: st.success("Aucune échéance dans les 5 prochains jours.")
        else: st.dataframe(credit_alerts, hide_index=True, column_config={"Reste": st.column_config.NumberColumn(format="%.0f FCFA")}, width="stretch")
    if v3.v3_ready():
        expiry=v3.expiry_alerts()
        if not expiry.empty:
            st.subheader("Lots à surveiller",icon=":material/event_busy:"); st.dataframe(expiry,hide_index=True,width="stretch")

elif page == "Caisse":
    products = db.products()
    clients = db.clients()
    st.header("Nouvelle vente", icon=":material/point_of_sale:")
    if products.empty:
        st.warning("Ajoutez au moins un produit avant de vendre.")
    else:
        if is_admin:
            sellers = db.sellers()
            if sellers.empty:
                st.warning("Ajoutez un vendeur dans Réglages → Vendeurs et comptes avant de vendre.")
                st.stop()
            seller_map = dict(zip(sellers.Vendeur, sellers.id))
            seller_name = st.selectbox("Vendeur", list(seller_map))
            seller_id = int(seller_map[seller_name])
        else:
            seller_id = int(user["seller_id"])
            seller_name = user["display_name"]
        seller_store_id=v4.store_for_seller(seller_id) if v4.v4_ready() else 1
        if seller_store_id != 1:
            store_stock=db.store_inventory(seller_store_id); stock_map=dict(zip(store_stock.id,store_stock.Stock)); products=products.copy(); products["Stock"]=products.id.map(lambda identifier:int(stock_map.get(identifier,0)))
        product_map = dict(zip(products.Produit, products.to_dict("records")))
        scanned_name = ""
        if db.v2_ready():
            with st.expander("Scanner un code-barres", icon=":material/barcode_scanner:"):
                barcode = st.text_input("Code-barres", placeholder="Scannez avec un lecteur ou saisissez le code")
                camera = st.camera_input("Ou photographiez le code-barres")
                detected = v2_ui.decode_barcode(camera) if camera else ""
                lookup = detected or barcode.strip()
                if lookup:
                    found = db.find_product_by_barcode(lookup)
                    if found: scanned_name = found["Produit"]; st.success(f"Produit détecté : {scanned_name}")
                    else: st.warning("Aucun produit ne correspond à ce code-barres.")
        with st.form("mobile_add_cart"):
            product_names = list(product_map)
            product_name = st.selectbox("Produit", product_names, index=product_names.index(scanned_name) if scanned_name in product_names else 0)
            product = product_map[product_name]
            variant_row = None
            product_variants = v4.variants(int(product["id"])) if v4.v4_ready() else pd.DataFrame()
            active_variants=product_variants[product_variants.Actif.astype(bool)] if not product_variants.empty else product_variants
            if not active_variants.empty:
                variant_map={f"{r.Variante} — stock {int(r.Stock)}":r for _,r in active_variants.iterrows()}
                variant_label=st.selectbox("Variante",list(variant_map)); variant_row=variant_map[variant_label]
            available_stock=min(int(product["Stock"]),int(variant_row.Stock)) if variant_row is not None else int(product["Stock"])
            quantity = st.number_input("Quantité", min_value=1, max_value=max(1, available_stock), value=1, step=1)
            if st.form_submit_button("Ajouter au ticket", type="primary"):
                if available_stock < quantity:
                    st.error("Stock insuffisant.")
                else:
                    variant_id=int(variant_row.id) if variant_row is not None else None
                    line = next((item for item in st.session_state.mobile_cart if item["id"] == product["id"] and item.get("variant_id")==variant_id), None)
                    if line:
                        line["quantity"] += int(quantity)
                    else:
                        item_name=product_name+(f" — {variant_row.Variante}" if variant_row is not None else "")
                        price=float(product["Vente"])+(float(variant_row.Ajustement_prix) if variant_row is not None else 0)
                        st.session_state.mobile_cart.append({"id": int(product["id"]), "variant_id":variant_id, "name": item_name, "quantity": int(quantity), "sale_price": price})
                    st.rerun()
        if st.session_state.mobile_cart:
            cart = pd.DataFrame(st.session_state.mobile_cart)
            cart["Total"] = cart.quantity * cart.sale_price
            st.subheader("Ticket", icon=":material/receipt_long:")
            st.dataframe(cart[["name", "quantity", "Total"]], hide_index=True)
            gross = float(cart.Total.sum())
            reduction_type = st.segmented_control("Réduction", ["Aucune", "Montant", "Pourcentage"], default="Aucune") if permissions["discount"] else "Aucune"
            discount = 0.0
            if reduction_type == "Montant":
                discount = st.number_input("Réduction (FCFA)", min_value=0.0, max_value=gross, step=100.0)
            elif reduction_type == "Pourcentage":
                percent = st.number_input("Réduction (%)", min_value=0.0, max_value=100.0, step=1.0)
                discount = gross * percent / 100
            total = gross - discount
            st.metric("À payer", fcfa(total))
            client_map = {"Vente comptant": None} | dict(zip(clients.Client, clients.id))
            client_name = st.selectbox("Client", list(client_map))
            payment_methods = ["Especes", "Wave", "Orange Money", "Carte"] + (["Credit"] if permissions["credit"] else [])
            method = st.selectbox("Paiement", payment_methods)
            if method == "Credit":
                paid = 0.0
                st.caption("Vente entièrement à crédit. Pour un acompte, choisissez son mode de paiement et saisissez le montant reçu.")
            else:
                paid = st.number_input("Montant reçu", min_value=0.0, value=total, step=100.0)
            is_credit = method == "Credit" or paid < total
            credit_days = st.number_input("Durée du crédit (jours)", min_value=1, value=30, step=1) if is_credit else 0
            due_date = date.today() + timedelta(days=int(credit_days)) if is_credit else None
            credit_ready = db.v2_ready()
            if due_date:
                st.info(f"Échéance prévue : {due_date:%d/%m/%Y}")
                if not credit_ready: st.warning("Exécutez la migration Supabase mise à jour avant d'enregistrer une vente à crédit.")
            discount_percent=(discount/gross*100) if gross else 0
            approval=v4.approval_settings() if v4.v4_ready() else {"configured":False,"threshold":101}
            pin_required=not is_admin and approval["configured"] and discount_percent>=float(approval["threshold"])
            approval_pin=st.text_input("PIN administrateur requis pour cette remise",type="password",max_chars=4) if pin_required else ""
            with st.container(horizontal=True, horizontal_alignment="distribute"):
                if st.button("Valider la vente", type="primary", icon=":material/check_circle:"):
                    if is_credit and not permissions["credit"]:
                        st.error("Ce compte vendeur n'est pas autorisé à faire une vente à crédit.")
                    elif is_credit and not credit_ready:
                        st.error("La migration Supabase doit être installée avant les nouvelles échéances de crédit.")
                    elif is_credit and client_map[client_name] is None:
                        st.error("Sélectionnez un client pour une vente à crédit.")
                    elif pin_required and not v4.verify_admin_pin(approval_pin,int(user["id"]),"REMISE_IMPORTANTE",discount,f"Remise {discount_percent:.1f}%"):
                        st.error("PIN administrateur incorrect.")
                    else:
                        if v4.v4_ready(): ticket, saved_gross, saved_total = v4.atomic_save_sale(st.session_state.mobile_cart, seller_id, client_map[client_name], min(paid,total), method, discount, due_date, seller_store_id)
                        else: ticket, saved_gross, saved_total = db.save_sale(st.session_state.mobile_cart, seller_id, client_map[client_name], min(paid,total), method, discount, due_date)
                        settings = db.get_settings() if db.v2_ready() else {}
                        receipt_args = (ticket, st.session_state.mobile_cart, seller_name, client_name, saved_gross, discount, saved_total, paid, method, settings)
                        st.session_state.mobile_receipt = make_receipt(*receipt_args)
                        st.session_state.mobile_receipt_pdf = make_receipt_pdf(*receipt_args)
                        client_phone = ""
                        if client_map[client_name] is not None and not clients.empty:
                            client_phone = str(clients.loc[clients.id == client_map[client_name], "Telephone"].iloc[0] or "")
                        st.session_state.mobile_receipt_info = {"ticket":ticket,"total":saved_total,"phone":client_phone}
                        try:
                            if db.v2_ready(): db.log_action(int(user["id"]), "VENTE", f"Ticket #{ticket} - {saved_total} FCFA")
                        except Exception: pass
                        st.session_state.mobile_cart = []
                        st.success(f"Vente enregistrée. Monnaie : {fcfa(max(0,paid-saved_total))}")
                if st.button("Vider", icon=":material/delete:"):
                    st.session_state.mobile_cart = []
                    st.rerun()
    if st.session_state.mobile_receipt:
        st.download_button("Télécharger le ticket", st.session_state.mobile_receipt, file_name="ticket.html", mime="text/html", icon=":material/download:")
        if st.session_state.mobile_receipt_pdf:
            st.download_button("Télécharger le ticket PDF", st.session_state.mobile_receipt_pdf, file_name="ticket.pdf", mime="application/pdf", icon=":material/picture_as_pdf:")
        if st.session_state.mobile_receipt_info:
            info = st.session_state.mobile_receipt_info
            st.link_button("Partager par WhatsApp", v2_ui.whatsapp_receipt_link(info["phone"], info["ticket"], info["total"]), icon=":material/share:")

elif page == "Produits":
    inventory = db.products()
    st.header("Produits et stock", icon=":material/inventory_2:")
    suppliers = db.suppliers()
    supplier_map = {"Sans fournisseur": None} | dict(zip(suppliers.Fournisseur, suppliers.id))
    with st.expander("Ajouter un produit", icon=":material/add_circle:", expanded=inventory.empty):
        with st.form("mobile_product"):
            name = st.text_input("Nom du produit")
            category = st.text_input("Catégorie", placeholder="Ex. Boissons")
            purchase = st.number_input("Prix d'achat (FCFA)", min_value=0.0, step=100.0)
            sale = st.number_input("Prix de vente (FCFA)", min_value=0.0, step=100.0)
            initial_stock = st.number_input("Quantité initiale", min_value=0, step=1)
            minimum = st.number_input("Seuil d'alerte", min_value=0, step=1)
            supplier_name = st.selectbox("Fournisseur", list(supplier_map))
            if st.form_submit_button("Ajouter le produit", type="primary", icon=":material/add:"):
                if not name.strip():
                    st.error("Le nom du produit est obligatoire.")
                elif sale <= 0:
                    st.error("Le prix de vente doit être supérieur à zéro.")
                else:
                    try:
                        db.add_product(name, category, purchase, sale, int(initial_stock), int(minimum), supplier_map[supplier_name])
                        st.success("Produit ajouté.")
                        st.rerun()
                    except Exception:
                        st.error("Ce produit existe déjà. Choisissez un autre nom.")
    v3_ui.product_list_download(inventory)
    st.dataframe(inventory, hide_index=True, column_config={"Achat": st.column_config.NumberColumn(format="%.0f FCFA"), "Vente": st.column_config.NumberColumn(format="%.0f FCFA"), "Photo":st.column_config.ImageColumn("Photo")})
    if not inventory.empty:
        with st.container(border=True):
            product_name = st.selectbox("Produit à modifier", inventory.Produit.tolist())
            record = inventory.loc[inventory.Produit == product_name].iloc[0]
            mode = st.segmented_control("Modification", ["Définir", "Ajouter", "Retirer"], default="Définir")
            amount = st.number_input("Quantité", min_value=0 if mode == "Définir" else 1, value=int(record.Stock) if mode == "Définir" else 1, step=1)
            if st.button("Enregistrer le stock", type="primary", icon=":material/save:"):
                try:
                    if mode == "Définir": db.set_stock(int(record.id), int(amount))
                    else: db.adjust_stock(int(record.id), int(amount) if mode == "Ajouter" else -int(amount))
                    st.success("Stock mis à jour.")
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
        if db.v2_ready():
            with st.expander("Code-barres et photo du produit", icon=":material/add_a_photo:"):
                detail_name = st.selectbox("Produit à identifier", inventory.Produit.tolist(), key="detail_product")
                detail_row = inventory.loc[inventory.Produit == detail_name].iloc[0]; detail_id = int(detail_row.id)
                current_photo = str(detail_row.Photo or "")
                if current_photo: st.image(current_photo, caption=detail_name, width=220)
                barcode = st.text_input("Code-barres", value=str(detail_row.Code_barres or ""))
                photo_file = st.file_uploader("Choisir une photo", type=["jpg","jpeg","png","webp"], key=f"photo_{detail_id}")
                camera_photo = st.camera_input("Ou prendre une photo", key=f"camera_{detail_id}")
                if st.button("Enregistrer le code-barres et la photo", type="primary", key=f"save_details_{detail_id}"):
                    try:
                        uploaded = camera_photo or photo_file; photo_url = current_photo
                        if uploaded is not None:
                            content = uploaded.getvalue()
                            if len(content) > 5 * 1024 * 1024: raise ValueError("La photo dépasse 5 Mo.")
                            photo_url = db.upload_product_photo(detail_id, getattr(uploaded,"name","camera.jpg"), content, getattr(uploaded,"type","image/jpeg"))
                        db.update_product_details(detail_id, barcode, photo_url); db.log_action(int(user["id"]), "PRODUIT_IDENTIFIE", detail_name); st.success("Code-barres et photo enregistrés."); st.rerun()
                    except ValueError as error: st.error(str(error))
                    except Exception as error: st.error(f"Impossible d'enregistrer la photo : {error}")

elif page == "Achats":
    st.header("Achats fournisseurs", icon=":material/local_shipping:")
    inventory = db.products(); suppliers = db.suppliers()
    if inventory.empty:
        st.warning("Ajoutez d'abord un produit.")
    else:
        product_map = dict(zip(inventory.Produit, inventory.to_dict("records")))
        supplier_names = ["Sans fournisseur"] + suppliers.Fournisseur.tolist()
        with st.form("mobile_purchase"):
            product_name = st.selectbox("Produit reçu", list(product_map))
            quantity = st.number_input("Quantité reçue", min_value=1, step=1)
            default_cost = float(product_map[product_name]["Achat"] or 0)
            unit_cost = st.number_input("Prix d'achat unitaire (FCFA)", min_value=0.0, value=default_cost, step=100.0)
            supplier_name = st.selectbox("Fournisseur", supplier_names)
            if st.form_submit_button("Enregistrer la livraison", type="primary", icon=":material/add_business:"):
                try:
                    db.register_purchase(int(product_map[product_name]["id"]), int(quantity), float(unit_cost), "" if supplier_name == "Sans fournisseur" else supplier_name)
                    st.success("Achat enregistré, stock augmenté et dépense ajoutée."); st.rerun()
                except ValueError as error: st.error(str(error))
        st.dataframe(db.products(), hide_index=True)

elif page == "Clients":
    with st.form("mobile_client"):
        name = st.text_input("Nom du client"); phone = st.text_input("Téléphone"); email = st.text_input("E-mail"); address = st.text_input("Adresse")
        if st.form_submit_button("Ajouter le client", type="primary"):
            try: db.add_client(name, phone, email, address); st.success("Client ajouté.")
            except Exception: st.error("Le nom du client est obligatoire et doit être unique.")
    st.dataframe(db.clients(), hide_index=True)

elif page == "Fournisseurs":
    with st.form("mobile_supplier"):
        name = st.text_input("Nom du fournisseur"); contact = st.text_input("Contact"); phone = st.text_input("Téléphone"); email = st.text_input("E-mail"); address = st.text_input("Adresse")
        if st.form_submit_button("Ajouter le fournisseur", type="primary"):
            try: db.add_supplier(name, contact, phone, email, address); st.success("Fournisseur ajouté.")
            except Exception: st.error("Le nom du fournisseur est obligatoire et doit être unique.")
    st.dataframe(db.suppliers(), hide_index=True)
    if v3.v3_ready():
        orders = v3.purchase_orders()
        if not orders.empty:
            st.subheader("Commandes et sommes à payer")
            supplier_name = st.selectbox("Filtrer par fournisseur", ["Tous"] + sorted(orders.Fournisseur.unique().tolist()))
            if supplier_name != "Tous":
                orders = orders[orders.Fournisseur == supplier_name]
            st.metric("Reste à payer sur les commandes", fcfa(float(orders.Reste.sum())))
            st.dataframe(orders, hide_index=True)
            if st.button("Enregistrer un règlement fournisseur"):
                st.session_state.mobile_page = "Commandes"
                st.rerun()



elif page == "Crédits":
    st.header("Crédits et historique clients", icon=":material/account_balance_wallet:")
    if v2_ui.migration_required(): st.stop()
    if db.v2_ready():
        alerts = db.credit_alerts()
        if alerts.empty: st.success("Aucune échéance dans les 5 prochains jours.")
        else:
            st.warning(f"{len(alerts)} crédit(s) nécessitent votre attention.", icon=":material/notifications_active:")
            st.dataframe(alerts, hide_index=True, column_config={"Reste": st.column_config.NumberColumn(format="%.0f FCFA")}, width="stretch")
            if st.button("Préparer une relance WhatsApp"):
                st.session_state.mobile_page = "Relances"
                st.rerun()
    customers = db.clients()
    if customers.empty:
        st.info("Ajoutez d'abord un client dans la liste des clients.")
    else:
        customer_map = dict(zip(customers.Client, customers.id))
        customer_name = st.selectbox("Client", list(customer_map))
        history = db.client_history(int(customer_map[customer_name]))
        balance = float(history.Reste.sum()) if not history.empty else 0.0
        st.metric("Dette totale", fcfa(balance))
        st.dataframe(history, hide_index=True, column_config={"Total": st.column_config.NumberColumn(format="%.0f FCFA"), "Paye": st.column_config.NumberColumn(format="%.0f FCFA"), "Reste": st.column_config.NumberColumn(format="%.0f FCFA")})
        if db.v2_ready() and balance > 0:
            debts = history[history.Reste > 0]
            ticket_map = {f"Ticket #{int(row.Ticket)} — reste {fcfa(float(row.Reste))}": row for _, row in debts.iterrows()}
            with st.form("credit_due_date"):
                due_ticket_label = st.selectbox("Crédit à planifier", list(ticket_map)); due_row = ticket_map[due_ticket_label]
                duration = st.number_input("Nouveau délai (jours)", min_value=1, value=30, step=1)
                calculated_due = date.today() + timedelta(days=int(duration)); st.caption(f"Nouvelle échéance : {calculated_due:%d/%m/%Y}")
                if st.form_submit_button("Enregistrer l'échéance"):
                    try:
                        db.set_credit_due_date(int(due_row.Ticket), calculated_due); db.log_action(int(user["id"]), "ECHEANCE_CREDIT", f"Ticket #{int(due_row.Ticket)} - {calculated_due}"); st.success("Échéance enregistrée."); st.rerun()
                    except ValueError as error: st.error(str(error))
            with st.form("credit_payment"):
                ticket_label = st.selectbox("Vente à rembourser", list(ticket_map)); debt_row = ticket_map[ticket_label]
                amount = st.number_input("Montant du remboursement", min_value=1.0, max_value=float(debt_row.Reste), step=100.0)
                method = st.selectbox("Mode de règlement", ["Especes", "Wave", "Orange Money", "Carte"])
                if st.form_submit_button("Enregistrer le remboursement", type="primary"):
                    try:
                        db.add_credit_payment(int(customer_map[customer_name]), int(debt_row.Ticket), amount, method, int(user["id"]))
                        db.log_action(int(user["id"]), "REMBOURSEMENT_CREDIT", f"{customer_name} - ticket #{int(debt_row.Ticket)} - {amount}")
                        st.success("Remboursement enregistré."); st.rerun()
                    except ValueError as error: st.error(str(error))
            st.subheader("Paiements reçus"); st.dataframe(db.credit_payments(int(customer_map[customer_name])), hide_index=True, width="stretch")
        if not history.empty:
            st.download_button("Exporter l'historique client", history.to_csv(index=False).encode("utf-8-sig"), file_name=f"historique_{customer_name}.csv", mime="text/csv", icon=":material/download:")

elif page == "Comptes":
    st.header("Vendeurs et comptes", icon=":material/manage_accounts:")
    with st.form("mobile_seller"):
        name = st.text_input("Nom du vendeur"); phone = st.text_input("Téléphone"); email = st.text_input("E-mail")
        username = st.text_input("Nom d'utilisateur"); password = st.text_input("Mot de passe", type="password"); confirm = st.text_input("Confirmer le mot de passe", type="password")
        if st.form_submit_button("Créer le vendeur", type="primary"):
            if len(name.strip()) < 2 or len(username.strip()) < 3 or len(password) < 8:
                st.error("Nom : 2 caractères ; identifiant : 3 ; mot de passe : 8.")
            elif password != confirm:
                st.error("Les mots de passe ne correspondent pas.")
            else:
                try: db.create_seller_with_user(name, phone, email, username, password); st.success("Vendeur et compte créés.")
                except Exception: st.error("Le nom ou l'identifiant existe déjà.")
    st.dataframe(db.users(), hide_index=True)

elif page in ("Rapports", "Historique"):
    st.header("Historique des ventes" if page == "Historique" else "Rapports", icon=":material/bar_chart:")
    period = st.date_input("Période", value=(date.today(), date.today()))
    if len(period) != 2:
        st.info("Sélectionnez une date de début et une date de fin.")
        st.stop()
    start, end = period
    sales = db.report(start, end)
    expenses = db.expenses(start, end)
    total_sales = float(sales.Total.sum()) if not sales.empty else 0.0
    total_expenses = float(expenses.Montant.sum()) if not expenses.empty else 0.0
    with st.container(border=True):
        st.metric("Ventes", fcfa(total_sales))
        st.metric("Dépenses", fcfa(total_expenses))
        st.metric("Solde", fcfa(total_sales-total_expenses))
    st.dataframe(sales, hide_index=True)
    performance = db.product_performance(start, end)
    if not performance.empty:
        st.subheader("Bénéfice et produits vendus", icon=":material/trending_up:")
        st.metric("Bénéfice brut estimé", fcfa(float(performance.Benefice.sum())))
        st.dataframe(performance, hide_index=True, column_config={"Chiffre": st.column_config.NumberColumn(format="%.0f FCFA"), "Benefice": st.column_config.NumberColumn(format="%.0f FCFA")})
    with st.expander("Ajouter une dépense", icon=":material/payments:"):
        with st.form("mobile_expense"):
            label = st.text_input("Libellé", placeholder="Ex. Transport, loyer, électricité")
            amount = st.number_input("Montant (FCFA)", min_value=0.0, step=100.0)
            if st.form_submit_button("Enregistrer la dépense", type="primary"):
                if not label.strip() or amount <= 0: st.error("Renseignez un libellé et un montant positif.")
                else: db.add_expense(label, amount); st.success("Dépense enregistrée."); st.rerun()
    st.subheader("Dépenses")
    st.dataframe(expenses, hide_index=True)
    export_sales = sales.to_csv(index=False).encode("utf-8-sig")
    export_stock = db.products().to_csv(index=False).encode("utf-8-sig")
    with st.container(horizontal=True):
        st.download_button("Exporter les ventes", export_sales, file_name=f"ventes_{start}_{end}.csv", mime="text/csv")
        st.download_button("Exporter le stock", export_stock, file_name="stock.csv", mime="text/csv")
    if not sales.empty:
        with st.expander("Corriger ou supprimer une vente", icon=":material/edit_note:"):
            ticket_map = {
                f"Ticket #{row.Ticket} · {row.Date} · {row.Client} · {fcfa(float(row.Total))}": int(row.Ticket)
                for _, row in sales.iterrows()
            }
            ticket_label = st.selectbox("Vente à gérer", list(ticket_map))
            sale_id = ticket_map[ticket_label]
            sale, sale_items = db.sale_details(sale_id)
            st.dataframe(
                sale_items,
                hide_index=True,
                column_config={"Prix": st.column_config.NumberColumn(format="%.0f FCFA"), "Total": st.column_config.NumberColumn(format="%.0f FCFA")},
            )
            clients = db.clients()
            client_options = {"Vente comptant": None} | dict(zip(clients.Client, clients.id))
            client_names = list(client_options)
            selected_client = next((name for name, identifier in client_options.items() if identifier == sale["client_id"]), "Vente comptant")
            with st.form(f"edit_sale_{sale_id}"):
                client_name = st.selectbox("Client", client_names, index=client_names.index(selected_client))
                methods = ["Especes", "Wave", "Orange Money", "Carte", "Credit"]
                payment = st.selectbox("Paiement", methods, index=methods.index(sale["payment_method"]) if sale["payment_method"] in methods else 0)
                paid = st.number_input("Montant encaissé", min_value=0.0, value=float(sale["paid"]), step=100.0)
                discount = st.number_input("Réduction (FCFA)", min_value=0.0, value=float(sale["discount"]), max_value=float(sale_items.Total.sum()), step=100.0)
                if st.form_submit_button("Enregistrer la correction", type="primary", icon=":material/save:"):
                    try:
                        _, new_total = db.update_sale(sale_id, client_options[client_name], paid, payment, discount)
                        st.success(f"Vente corrigée. Nouveau total : {fcfa(new_total)}")
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
            if not sale_items.empty:
                if st.button("Traiter un retour ou un échange"):
                    st.session_state.mobile_page = "Retours V3"
                    st.rerun()
            st.warning("Supprimer une vente est définitif. Les quantités vendues seront remises en stock.", icon=":material/warning:")
            confirm_delete = st.checkbox("Je confirme la suppression de cette vente", key=f"confirm_delete_sale_{sale_id}")
            if st.button("Supprimer définitivement", icon=":material/delete:", key=f"delete_sale_{sale_id}"):
                if not confirm_delete:
                    st.error("Cochez la confirmation avant de supprimer la vente.")
                else:
                    try:
                        db.delete_sale(sale_id)
                        if db.v2_ready(): db.log_action(int(user["id"]), "VENTE_SUPPRIMEE", f"Ticket #{sale_id}")
                        st.success("Vente supprimée et stock restauré.")
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))

elif page == "Tableau V2":
    v2_ui.dashboard_page()

elif page == "Clôture":
    daily_ui.cash_page(user)

elif page == "Paiements":
    daily_ui.payments_page(user)

elif page == "Relances":
    daily_ui.reminders_page(user)

elif page == "Inventaire":
    v2_ui.inventory_page(user)

elif page == "Boutiques":
    v2_ui.stores_page(user)

elif page == "Sécurité":
    v2_ui.security_page(user)
    workflow_ui.preferences_panel(user)

elif page == "Paramètres":
    v2_ui.settings_page(user)
    features_ui.invoice_settings(user)

elif page == "Factures":
    from business_pdf import make_business_document_pdf
    st.caption("Téléchargez une facture à partir d'une vente enregistrée, sans ressaisir les produits.")
    period = st.date_input("Période des ventes", value=(date.today().replace(day=1), date.today()))
    if len(period) != 2:
        st.info("Sélectionnez une date de début et une date de fin.")
        st.stop()
    sales = db.report(*period)
    if sales.empty:
        st.info("Aucune vente sur cette période.")
    else:
        labels = {f"Vente #{int(r.Ticket)} · {r.Client} · {fcfa(r.Total)}": r
                  for _, r in sales.iterrows()}
        selected = st.selectbox("Vente à facturer", list(labels))
        row = labels[selected]
        sale_id = int(row.Ticket)
        sale, items = db.sale_details(sale_id)
        st.dataframe(items, hide_index=True)
        total = float(sale["total"])
        paid = float(sale["paid"])
        remaining = max(total - paid, 0)
        st.metric("Total", fcfa(total))
        st.metric("Reste à payer", fcfa(remaining))
        st.metric("État du paiement", features.payment_status(total, paid))
        if remaining > 0:
            with st.form("invoice_due"):
                due = st.date_input("Échéance de la facture", value=date.fromisoformat(str(sale["due_date"])[:10]) if sale.get("due_date") else date.today()+timedelta(days=30))
                if st.form_submit_button("Enregistrer l’échéance de la facture"):
                    db.set_credit_due_date(sale_id, due)
                    st.rerun()
        workflow_ui.invoice_panel('VENTE', sale_id, user)

elif page == "Documents":
    v3_ui.documents_page(user)

elif page == "Commandes":
    v3_ui.purchase_orders_page(user)

elif page == "Retours V3":
    v3_ui.returns_page(user)

elif page == "Fidélité":
    v3_ui.loyalty_page(user)

elif page == "Lots":
    v3_ui.lots_page(user)

elif page == "Permissions":
    v3_ui.permissions_page(user)

elif page == "Caisse secours":
    v3_ui.offline_page(user)

elif page == "Impression":
    v4_ui.impression_page(user)

elif page == "Recherche":
    v4_ui.search_page()

elif page == "Importation":
    v4_ui.import_page(user)

elif page == "Variantes":
    v4_ui.variants_page(user)

elif page == "Commissions":
    v4_ui.commissions_page(user)

elif page == "Approbations":
    v4_ui.approvals_page(user)

elif page == "Automatisation":
    v4_ui.automation_page(user)

elif page == "Propriétaire":
    v4_ui.owner_page()

elif page == "Stock":
    v3_ui.stock_readonly_page()
