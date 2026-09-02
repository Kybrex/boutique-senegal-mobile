"""Version mobile iPhone de Boutique Senegal.

Lancer avec : streamlit run iphone_app.py --server.port 8502
"""
from __future__ import annotations

from datetime import date, timedelta
import pandas as pd
import streamlit as st

from receipt import make_receipt, make_receipt_pdf
import v2_ui


st.set_page_config(page_title="Boutique Senegal Mobile", page_icon=":material/storefront:", layout="centered")


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

db.init_db()
st.session_state.setdefault("mobile_cart", [])
st.session_state.setdefault("mobile_receipt", None)
st.session_state.setdefault("mobile_receipt_pdf", None)
st.session_state.setdefault("mobile_receipt_info", None)
st.session_state.setdefault("mobile_page", "Accueil")


def fcfa(value: float) -> str:
    return f"{value:,.0f} FCFA".replace(",", " ")


def sign_out() -> None:
    st.session_state.pop("mobile_user", None)
    st.session_state.mobile_cart = []
    st.rerun()


if db.user_count() == 0:
    st.title("Boutique Senegal", icon=":material/storefront:")
    st.caption("Version mobile pour iPhone")
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

if "mobile_user" not in st.session_state:
    st.title("Boutique Senegal", icon=":material/storefront:")
    st.caption("Caisse et stock — version mobile")
    with st.form("mobile_login"):
        username = st.text_input("Nom d'utilisateur")
        password = st.text_input("Mot de passe", type="password")
        if st.form_submit_button("Se connecter", type="primary"):
            user = db.authenticate(username, password)
            if user:
                st.session_state.mobile_user = user
                st.session_state.mobile_page = "Accueil" if user["role"] == "admin" else "Caisse"
                try:
                    if db.v2_ready(): db.log_action(int(user["id"]), "CONNEXION", user["display_name"])
                except Exception:
                    pass
                st.rerun()
            st.error("Identifiant ou mot de passe incorrect.")
    st.stop()

user = st.session_state.mobile_user
is_admin = user["role"] == "admin"
permissions = v3.user_permissions(user)
st.title("Boutique Senegal", icon=":material/storefront:")
st.caption(f"{user['display_name']} · {'Administrateur' if is_admin else 'Vendeur'}")

if is_admin and v4.v4_ready() and not st.session_state.get("v4_session_tasks_done"):
    try:
        st.session_state.v4_notifications=v4.refresh_notifications()
        st.session_state.v4_backup_status=v4.automatic_backup_if_due()
    except Exception as error:
        st.session_state.v4_backup_status=f"indisponible: {str(error)[:120]}"
    st.session_state.v4_session_tasks_done=True

if is_admin:
    pages = [
        ("Accueil", ":material/home:"),
        ("Caisse", ":material/point_of_sale:"),
        ("Produits", ":material/inventory_2:"),
        ("Achats", ":material/local_shipping:"),
        ("Contacts", ":material/contacts:"),
        ("Crédits", ":material/account_balance_wallet:"),
        ("Comptes", ":material/manage_accounts:"),
        ("Rapports", ":material/analytics:"),
        ("Tableau V2", ":material/monitoring:"),
        ("Clôture", ":material/point_of_sale:"),
        ("Inventaire", ":material/fact_check:"),
        ("Boutiques", ":material/store:"),
        ("Sécurité", ":material/security:"),
        ("Paramètres", ":material/settings:"),
        ("Documents", ":material/description:"),
        ("Commandes", ":material/inventory:"),
        ("Retours V3", ":material/assignment_return:"),
        ("Fidélité", ":material/loyalty:"),
        ("Lots", ":material/event_busy:"),
        ("Permissions", ":material/admin_panel_settings:"),
        ("Caisse secours", ":material/cloud_off:"),
        ("Impression", ":material/print:"),
        ("Recherche", ":material/search:"),
        ("Importation", ":material/upload_file:"),
        ("Variantes", ":material/style:"),
        ("Commissions", ":material/percent:"),
        ("Approbations", ":material/password:"),
        ("Automatisation", ":material/notifications_active:"),
        ("Propriétaire", ":material/leaderboard:"),
    ]
else:
    pages = [("Caisse", ":material/point_of_sale:")]
    if permissions["stock"]: pages.append(("Stock", ":material/inventory_2:"))
    if permissions["returns"] and v3.v3_ready(): pages.append(("Retours V3", ":material/assignment_return:"))

page_names = [name for name, _ in pages]
if st.session_state.mobile_page not in page_names:
    st.session_state.mobile_page = "Accueil" if is_admin else "Caisse"

with st.sidebar:
    st.header("Boutique Senegal")
    st.caption("MENU")
    with st.container(border=True, gap="small"):
        for name, icon in pages:
            if st.button(
                name,
                icon=icon,
                type="primary" if st.session_state.mobile_page == name else "secondary",
                key=f"mobile_menu_{name}",
                width="stretch",
            ):
                st.session_state.mobile_page = name
                st.rerun()
    st.space("small")
    st.button("Se déconnecter", icon=":material/logout:", on_click=sign_out, width="stretch")

page = st.session_state.mobile_page

if page == "Accueil":
    summary = db.today_summary().iloc[0]
    alerts = db.low_stock()
    st.header("Aujourd'hui", icon=":material/today:")
    with st.container(border=True):
        st.metric("Ventes", fcfa(float(summary.sales)))
        st.metric("Tickets", int(summary.transactions))
        st.metric("Alertes de stock", len(alerts))
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
                st.warning("Ajoutez un vendeur avant de vendre.")
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
                        if v4.v4_ready(): ticket, saved_gross, saved_total = v4.atomic_save_sale(st.session_state.mobile_cart, seller_id, client_map[client_name], paid, method, discount, due_date, seller_store_id)
                        else: ticket, saved_gross, saved_total = db.save_sale(st.session_state.mobile_cart, seller_id, client_map[client_name], paid, method, discount, due_date)
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
                        st.success(f"Vente enregistrée. Monnaie : {fcfa(paid-saved_total)}")
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

elif page == "Contacts":
    st.header("Clients et fournisseurs", icon=":material/contacts:")
    client_tab, supplier_tab = st.tabs(["Clients", "Fournisseurs"])
    with client_tab:
        with st.form("mobile_client"):
            name = st.text_input("Nom du client"); phone = st.text_input("Téléphone"); email = st.text_input("E-mail"); address = st.text_input("Adresse")
            if st.form_submit_button("Ajouter le client", type="primary"):
                try: db.add_client(name, phone, email, address); st.success("Client ajouté.")
                except Exception: st.error("Le nom du client est obligatoire et doit être unique.")
        st.dataframe(db.clients(), hide_index=True)
    with supplier_tab:
        with st.form("mobile_supplier"):
            name = st.text_input("Nom du fournisseur"); contact = st.text_input("Contact"); phone = st.text_input("Téléphone"); email = st.text_input("E-mail"); address = st.text_input("Adresse")
            if st.form_submit_button("Ajouter le fournisseur", type="primary"):
                try: db.add_supplier(name, contact, phone, email, address); st.success("Fournisseur ajouté.")
                except Exception: st.error("Le nom du fournisseur est obligatoire et doit être unique.")
        st.dataframe(db.suppliers(), hide_index=True)

elif page == "Crédits":
    st.header("Crédits et historique clients", icon=":material/account_balance_wallet:")
    if v2_ui.migration_required(): st.stop()
    if db.v2_ready():
        alerts = db.credit_alerts()
        if alerts.empty: st.success("Aucune échéance dans les 5 prochains jours.")
        else:
            st.warning(f"{len(alerts)} crédit(s) nécessitent votre attention.", icon=":material/notifications_active:")
            st.dataframe(alerts, hide_index=True, column_config={"Reste": st.column_config.NumberColumn(format="%.0f FCFA")}, width="stretch")
            reminder_labels={f"{r.Client} - ticket #{int(r.Ticket)} - {r.Statut}":r for _,r in alerts.iterrows()}; reminder_label=st.selectbox("Rappel WhatsApp",list(reminder_labels)); st.link_button("Envoyer le rappel WhatsApp",v3_ui.credit_reminder_link(reminder_labels[reminder_label]),icon=":material/send:",width="stretch")
    customers = db.clients()
    if customers.empty:
        st.info("Ajoutez d'abord un client dans Contacts.")
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

elif page == "Rapports":
    st.header("Rapports", icon=":material/bar_chart:")
    start, end = st.date_input("Période", value=(date.today(), date.today()))
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
                st.subheader("Retour partiel")
                return_map = {f"{row.Produit} — vendu: {int(row.Quantite)}": row for _, row in sale_items.iterrows()}
                return_label = st.selectbox("Produit retourné", list(return_map), key=f"return_product_{sale_id}")
                return_row = return_map[return_label]
                return_quantity = st.number_input("Quantité retournée", min_value=1, max_value=int(return_row.Quantite), value=1, step=1, key=f"return_qty_{sale_id}")
                if st.button("Valider le retour", key=f"return_sale_{sale_id}"):
                    try:
                        new_total = db.return_sale_item(sale_id, int(return_row.product_id), int(return_quantity))
                        st.success(f"Retour enregistré, stock restauré. Nouveau total : {fcfa(new_total)}"); st.rerun()
                    except ValueError as error: st.error(str(error))
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
    v2_ui.cash_page(user)

elif page == "Inventaire":
    v2_ui.inventory_page(user)

elif page == "Boutiques":
    v2_ui.stores_page(user)

elif page == "Sécurité":
    v2_ui.security_page(user)

elif page == "Paramètres":
    v2_ui.settings_page(user)

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
