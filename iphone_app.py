"""Version mobile iPhone de Boutique Senegal.

Lancer avec : streamlit run iphone_app.py --server.port 8502
"""
from __future__ import annotations

from datetime import date
import pandas as pd
import streamlit as st

import db
from receipt import make_receipt
from supabase_client import configuration_error


st.set_page_config(page_title="Boutique Senegal Mobile", page_icon=":material/storefront:", layout="centered")
secret_error = configuration_error()
if secret_error:
    st.error("Configuration Supabase à corriger", icon=":material/key:")
    st.warning(secret_error)
    st.info("Ouvrez Manage app → Settings → Secrets, remplacez SUPABASE_KEY par la vraie clé secrète Supabase, puis redémarrez l'application.")
    st.stop()
db.init_db()
st.session_state.setdefault("mobile_cart", [])
st.session_state.setdefault("mobile_receipt", None)
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
                st.rerun()
            st.error("Identifiant ou mot de passe incorrect.")
    st.stop()

user = st.session_state.mobile_user
is_admin = user["role"] == "admin"
st.title("Boutique Senegal", icon=":material/storefront:")
st.caption(f"{user['display_name']} · {'Administrateur' if is_admin else 'Vendeur'}")

pages = [
    ("Accueil", ":material/home:"),
    ("Caisse", ":material/point_of_sale:"),
]
if is_admin:
    pages += [
        ("Produits", ":material/inventory_2:"),
        ("Achats", ":material/local_shipping:"),
        ("Contacts", ":material/contacts:"),
        ("Crédits", ":material/account_balance_wallet:"),
        ("Comptes", ":material/manage_accounts:"),
        ("Rapports", ":material/analytics:"),
    ]

page_names = [name for name, _ in pages]
if st.session_state.mobile_page not in page_names:
    st.session_state.mobile_page = "Accueil"

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
        product_map = dict(zip(products.Produit, products.to_dict("records")))
        with st.form("mobile_add_cart"):
            product_name = st.selectbox("Produit", list(product_map))
            product = product_map[product_name]
            quantity = st.number_input("Quantité", min_value=1, max_value=max(1, int(product["Stock"])), value=1, step=1)
            if st.form_submit_button("Ajouter au ticket", type="primary"):
                if int(product["Stock"]) < quantity:
                    st.error("Stock insuffisant.")
                else:
                    line = next((item for item in st.session_state.mobile_cart if item["id"] == product["id"]), None)
                    if line:
                        line["quantity"] += int(quantity)
                    else:
                        st.session_state.mobile_cart.append({"id": int(product["id"]), "name": product_name, "quantity": int(quantity), "sale_price": float(product["Vente"])})
                    st.rerun()
        if st.session_state.mobile_cart:
            cart = pd.DataFrame(st.session_state.mobile_cart)
            cart["Total"] = cart.quantity * cart.sale_price
            st.subheader("Ticket", icon=":material/receipt_long:")
            st.dataframe(cart[["name", "quantity", "Total"]], hide_index=True)
            gross = float(cart.Total.sum())
            reduction_type = st.segmented_control("Réduction", ["Aucune", "Montant", "Pourcentage"], default="Aucune")
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
            method = st.selectbox("Paiement", ["Especes", "Wave", "Orange Money", "Carte", "Credit"])
            paid = st.number_input("Montant reçu", min_value=0.0, value=total, step=100.0)
            with st.container(horizontal=True, horizontal_alignment="distribute"):
                if st.button("Valider la vente", type="primary", icon=":material/check_circle:"):
                    if paid < total and client_map[client_name] is None:
                        st.error("Sélectionnez un client pour une vente à crédit.")
                    else:
                        ticket, saved_gross, saved_total = db.save_sale(st.session_state.mobile_cart, seller_id, client_map[client_name], paid, method, discount)
                        st.session_state.mobile_receipt = make_receipt(ticket, st.session_state.mobile_cart, seller_name, client_name, saved_gross, discount, saved_total, paid, method)
                        st.session_state.mobile_cart = []
                        st.success(f"Vente enregistrée. Monnaie : {fcfa(paid-saved_total)}")
                if st.button("Vider", icon=":material/delete:"):
                    st.session_state.mobile_cart = []
                    st.rerun()
    if st.session_state.mobile_receipt:
        st.download_button("Télécharger le ticket", st.session_state.mobile_receipt, file_name="ticket.html", mime="text/html", icon=":material/download:")

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
    st.dataframe(inventory, hide_index=True, column_config={"Achat": st.column_config.NumberColumn(format="%.0f FCFA"), "Vente": st.column_config.NumberColumn(format="%.0f FCFA")})
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
                        st.success("Vente supprimée et stock restauré.")
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
