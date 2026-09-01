from __future__ import annotations
from datetime import date
import pandas as pd
import streamlit as st
import db
from receipt import make_receipt

st.set_page_config(page_title="Boutique Senegal", page_icon="S", layout="wide")
db.init_db()
st.session_state.setdefault("cart", [])
st.session_state.setdefault("receipt", None)
def fcfa(value: float) -> str: return f"{value:,.0f} FCFA".replace(",", " ")

if db.user_count() == 0:
    st.title("Boutique Senegal")
    st.subheader("Creer l'administrateur principal")
    st.info("Renseignez son nom, son nom d'utilisateur et son mot de passe. Cette etape apparait une seule fois.")
    with st.form("setup_admin"):
        name = st.text_input("Votre nom"); username = st.text_input("Nom d'utilisateur"); password = st.text_input("Mot de passe", type="password"); confirm = st.text_input("Confirmer le mot de passe", type="password")
        if st.form_submit_button("Creer l'administrateur"):
            if len(username) < 3 or len(password) < 8: st.error("Le nom d'utilisateur doit avoir 3 caracteres et le mot de passe 8 caracteres.")
            elif password != confirm: st.error("Les mots de passe ne correspondent pas.")
            else:
                try: db.create_user(username, name, password, "admin"); st.success("Administrateur cree. Connectez-vous.")
                except Exception: st.error("Ce nom d'utilisateur existe deja.")
    st.stop()

if "user" not in st.session_state:
    st.title("Boutique Senegal")
    st.subheader("Connexion")
    with st.form("login"):
        username = st.text_input("Nom d'utilisateur"); password = st.text_input("Mot de passe", type="password")
        if st.form_submit_button("Se connecter"):
            user = db.authenticate(username, password)
            if user: st.session_state.user = user; st.rerun()
            else: st.error("Nom d'utilisateur ou mot de passe incorrect.")
    st.stop()

user = st.session_state.user; admin = user["role"] == "admin"
st.title("Boutique Senegal")
st.caption(f"Connecte: {user['display_name']} | {'Administrateur' if admin else 'Vendeur'} | FCFA")
if st.sidebar.button("Se deconnecter"):
    st.session_state.pop("user"); st.session_state.cart = []; st.rerun()
menu = ["Tableau de bord", "Caisse"] + (["Produits et stock", "Clients et fournisseurs", "Vendeurs et comptes", "Rapports"] if admin else [])
page = st.sidebar.radio("Menu", menu)

if page == "Tableau de bord":
    summary = db.today_summary().iloc[0]; alerts = db.low_stock()
    a, b, c = st.columns(3); a.metric("Ventes aujourd'hui", fcfa(summary.sales)); b.metric("Tickets aujourd'hui", int(summary.transactions)); c.metric("Alertes de stock", len(alerts))
    st.subheader("Stock faible ou en rupture")
    if not alerts.empty: st.dataframe(alerts, hide_index=True)
    else: st.success("Aucune alerte de stock.")

elif page == "Produits et stock":
    suppliers = db.suppliers(); supplier_map = {"Aucun": None} | dict(zip(suppliers.Fournisseur, suppliers.id))
    st.subheader("Ajouter un produit")
    with st.form("product_form", clear_on_submit=True):
        name = st.text_input("Nom du produit"); category = st.text_input("Categorie"); supplier = st.selectbox("Fournisseur", list(supplier_map))
        a, b, c, d = st.columns(4); purchase = a.number_input("Prix d'achat (FCFA)", min_value=0.0, step=100.0); sale = b.number_input("Prix de vente (FCFA)", min_value=1.0, step=100.0); stock = c.number_input("Stock initial", min_value=0, step=1); minimum = d.number_input("Alerte minimum", min_value=0, step=1)
        if st.form_submit_button("Enregistrer le produit"):
            try: db.add_product(name, category, purchase, sale, stock, minimum, supplier_map[supplier]); st.success("Produit ajoute.")
            except Exception: st.error("Le nom du produit est obligatoire et doit etre unique.")
    inventory = db.products(); st.subheader("Inventaire"); st.dataframe(inventory, hide_index=True, column_config={"Achat": st.column_config.NumberColumn(format="%.0f FCFA"), "Vente": st.column_config.NumberColumn(format="%.0f FCFA")})
    if not inventory.empty:
        st.subheader("Modifier manuellement le stock")
        product_name = st.selectbox("Produit a modifier", inventory.Produit.tolist()); record = inventory.loc[inventory.Produit == product_name].iloc[0]
        change_mode = st.segmented_control("Type de modification", ["Definir la quantite exacte", "Ajouter", "Retirer"], default="Definir la quantite exacte")
        if change_mode == "Definir la quantite exacte":
            new_quantity = st.number_input("Nouvelle quantite exacte", min_value=0, value=int(record.Stock), step=1)
            if st.button("Enregistrer la quantite", type="primary"):
                db.set_stock(int(record.id), int(new_quantity)); st.success("Stock mis a jour."); st.rerun()
        else:
            amount = st.number_input("Quantite a ajouter" if change_mode == "Ajouter" else "Quantite a retirer", min_value=1, value=1, step=1)
            if st.button("Confirmer la modification", type="primary"):
                try:
                    db.adjust_stock(int(record.id), int(amount) if change_mode == "Ajouter" else -int(amount)); st.success("Stock mis a jour."); st.rerun()
                except ValueError as error: st.error(str(error))

elif page == "Clients et fournisseurs":
    client_tab, supplier_tab = st.tabs(["Clients", "Fournisseurs"])
    with client_tab:
        with st.form("client_form", clear_on_submit=True):
            name = st.text_input("Nom du client"); phone = st.text_input("Telephone du client"); email = st.text_input("Email du client"); address = st.text_input("Adresse du client")
            if st.form_submit_button("Ajouter le client"):
                try: db.add_client(name, phone, email, address); st.success("Client ajoute.")
                except Exception: st.error("Le nom du client est obligatoire et doit etre unique.")
        st.dataframe(db.clients(), hide_index=True)
    with supplier_tab:
        with st.form("supplier_form", clear_on_submit=True):
            name = st.text_input("Nom du fournisseur"); contact = st.text_input("Personne a contacter"); phone = st.text_input("Telephone du fournisseur"); email = st.text_input("Email du fournisseur"); address = st.text_input("Adresse du fournisseur")
            if st.form_submit_button("Ajouter le fournisseur"):
                try: db.add_supplier(name, contact, phone, email, address); st.success("Fournisseur ajoute.")
                except Exception: st.error("Le nom du fournisseur est obligatoire et doit etre unique.")
        st.dataframe(db.suppliers(), hide_index=True)

elif page == "Vendeurs et comptes":
    vendor_tab, account_tab = st.tabs(["Vendeurs", "Comptes de connexion"])
    with vendor_tab:
        st.caption("Chaque nouveau vendeur recoit son propre compte de connexion.")
        with st.form("seller_form", clear_on_submit=True):
            name = st.text_input("Nom du vendeur"); phone = st.text_input("Telephone"); email = st.text_input("Email du vendeur")
            username = st.text_input("Nom d'utilisateur du vendeur"); password = st.text_input("Mot de passe du vendeur", type="password"); confirm = st.text_input("Confirmer le mot de passe", type="password")
            if st.form_submit_button("Ajouter le vendeur et son compte"):
                if len(username) < 3 or len(password) < 8: st.error("Nom utilisateur : 3 caracteres minimum ; mot de passe : 8 caracteres minimum.")
                elif password != confirm: st.error("Les mots de passe ne correspondent pas.")
                else:
                    try: db.create_seller_with_user(name, phone, email, username, password); st.success("Vendeur et compte crees.")
                    except Exception: st.error("Le nom du vendeur ou le nom d'utilisateur existe deja.")
        st.dataframe(db.sellers(), hide_index=True)
    with account_tab:
        st.caption("L'administrateur principal est cree au premier lancement. Creez ici un compte distinct pour chaque vendeur.")
        accounts = db.users()
        if not accounts.empty: st.dataframe(accounts, hide_index=True)
        sellers = db.sellers()
        if sellers.empty: st.info("Ajoutez d'abord un vendeur.")
        else:
            seller_map = dict(zip(sellers.Vendeur, sellers.id))
            with st.form("user_form", clear_on_submit=True):
                seller_name = st.selectbox("Vendeur concerne", list(seller_map)); username = st.text_input("Nom d'utilisateur vendeur"); password = st.text_input("Mot de passe vendeur", type="password")
                if st.form_submit_button("Creer le compte vendeur"):
                    if len(username) < 3 or len(password) < 8: st.error("Nom utilisateur: 3 caracteres; mot de passe: 8 caracteres.")
                    else:
                        try: db.create_user(username, seller_name, password, "seller", int(seller_map[seller_name])); st.success("Compte vendeur cree.")
                        except Exception: st.error("Ce nom d'utilisateur existe deja.")

elif page == "Caisse":
    products = db.products(); clients = db.clients()
    if products.empty: st.warning("Un administrateur doit ajouter des produits avant d'utiliser la caisse.")
    elif not admin and not user.get("seller_id"): st.error("Ce compte vendeur n'est associe a aucun vendeur. Contactez l'administrateur.")
    else:
        if admin:
            sellers = db.sellers()
            if sellers.empty: st.warning("Ajoutez un vendeur avant d'utiliser la caisse."); st.stop()
            seller_map = dict(zip(sellers.Vendeur, sellers.id)); seller_name = st.selectbox("Vendeur", list(seller_map)); seller_id = int(seller_map[seller_name])
        else: seller_id = int(user["seller_id"]); seller_name = user["display_name"]
        client_map = {"Vente comptant / sans client": None} | dict(zip(clients.Client, clients.id)); client_name = st.selectbox("Client", list(client_map)); client_id = client_map[client_name]
        product_map = dict(zip(products.Produit, products.to_dict("records"))); product_name = st.selectbox("Produit", list(product_map)); product = product_map[product_name]
        quantity = st.number_input("Quantite", min_value=1, max_value=max(1, int(product["Stock"])), step=1)
        if st.button("Ajouter au ticket"):
            if product["Stock"] < quantity: st.error("Stock insuffisant.")
            else:
                line = next((item for item in st.session_state.cart if item["id"] == product["id"]), None)
                if line: line["quantity"] += quantity
                else: st.session_state.cart.append({"id": int(product["id"]), "name": product_name, "quantity": quantity, "sale_price": float(product["Vente"])})
        if st.session_state.cart:
            cart_df = pd.DataFrame(st.session_state.cart); cart_df["Total"] = cart_df.quantity * cart_df.sale_price
            st.subheader("Ticket en cours"); st.dataframe(cart_df[["name", "quantity", "sale_price", "Total"]], hide_index=True)
            gross = float(cart_df.Total.sum()); discount_kind = st.radio("Reduction", ["Aucune", "Montant FCFA", "Pourcentage"], horizontal=True)
            reduction = 0.0
            if discount_kind == "Montant FCFA": reduction = st.number_input("Reduction (FCFA)", min_value=0.0, max_value=gross, step=100.0)
            elif discount_kind == "Pourcentage": reduction = gross * st.number_input("Reduction (%)", min_value=0.0, max_value=100.0, step=1.0) / 100
            total = gross-reduction; st.metric("Total a payer", fcfa(total)); paid = st.number_input("Montant recu (FCFA)", min_value=0.0, value=total, step=100.0); method = st.selectbox("Mode de paiement", ["Especes", "Wave", "Orange Money", "Carte"])
            x, y = st.columns(2)
            if x.button("Valider la vente", type="primary"):
                if paid < total: st.error("Le montant recu est insuffisant.")
                else:
                    ticket, saved_gross, saved_total = db.save_sale(st.session_state.cart, seller_id, client_id, paid, method, reduction)
                    st.session_state.receipt = make_receipt(ticket, st.session_state.cart, seller_name, saved_gross, reduction, saved_total, paid, method); st.session_state.cart = []; st.success(f"Vente enregistree. Monnaie: {fcfa(paid-saved_total)}")
            if y.button("Vider le ticket"): st.session_state.cart = []; st.rerun()
    if st.session_state.receipt: st.download_button("Telecharger / imprimer le ticket", st.session_state.receipt, file_name="ticket.html", mime="text/html")

else:
    start, end = st.date_input("Periode", value=(date.today(), date.today()))
    sales = db.report(start, end); spend = db.expenses(start, end); total_sales = sales.Total.sum() if not sales.empty else 0; total_expenses = spend.Montant.sum() if not spend.empty else 0
    a, b, c = st.columns(3); a.metric("Ventes", fcfa(total_sales)); b.metric("Depenses", fcfa(total_expenses)); c.metric("Solde caisse", fcfa(total_sales-total_expenses))
    with st.form("expense_form", clear_on_submit=True):
        label = st.text_input("Nouvelle depense - libelle"); amount = st.number_input("Montant depense (FCFA)", min_value=0.0, step=100.0)
        if st.form_submit_button("Enregistrer la depense") and label and amount > 0: db.add_expense(label, amount); st.rerun()
    st.subheader("Ventes"); st.dataframe(sales, hide_index=True)
    st.subheader("Depenses"); st.dataframe(spend, hide_index=True)
