"""Implémentation Supabase de la couche de données Boutique Senegal."""
from __future__ import annotations

from datetime import date
import pandas as pd

from supabase_client import client, is_configured


def enabled() -> bool:
    return is_configured()


def _data(response) -> list[dict]:
    return response.data or []


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _table(name: str):
    return client().table(name)


def _one(name: str, **filters) -> dict | None:
    request = _table(name).select("*")
    for key, value in filters.items(): request = request.eq(key, value)
    rows = _data(request.limit(1).execute())
    return rows[0] if rows else None


def user_count() -> int:
    return len(_data(_table("users").select("id").execute()))


def create_user(username, display_name, password_hash, role, seller_id=None):
    _table("users").insert({"username": username, "display_name": display_name, "password_hash": password_hash, "role": role, "seller_id": seller_id}).execute()


def authenticate(username: str) -> dict | None:
    return _one("users", username=username, active=True)


def add_product(name, category, purchase, sale, stock, minimum, supplier_id):
    _table("products").insert({"name": name, "category": category, "purchase_price": purchase, "sale_price": sale, "stock": stock, "min_stock": minimum, "supplier_id": supplier_id}).execute()


def set_stock(product_id, stock): _table("products").update({"stock": stock}).eq("id", product_id).execute()


def adjust_stock(product_id, adjustment):
    product = _one("products", id=product_id)
    if product is None: raise ValueError("Produit introuvable")
    stock = int(product["stock"]) + adjustment
    if stock < 0: raise ValueError("Le stock ne peut pas être négatif")
    set_stock(product_id, stock)


def add_seller(name, phone, email): _table("sellers").insert({"name": name, "phone": phone, "email": email}).execute()


def create_seller_with_user(name, phone, email, username, password_hash):
    seller = _data(_table("sellers").insert({"name": name, "phone": phone, "email": email}).execute())[0]
    create_user(username, name, password_hash, "seller", seller["id"])


def add_supplier(name, contact, phone, email, address): _table("suppliers").insert({"name": name, "contact": contact, "phone": phone, "email": email, "address": address}).execute()
def add_client(name, phone, email, address): _table("clients").insert({"name": name, "phone": phone, "email": email, "address": address}).execute()


def products() -> pd.DataFrame:
    rows = _data(_table("products").select("*,suppliers(name)").order("name").execute())
    return _frame([{ "id": r["id"], "Produit": r["name"], "Categorie": r.get("category", ""), "Achat": r["purchase_price"], "Vente": r["sale_price"], "Stock": r["stock"], "Minimum": r["min_stock"], "Fournisseur": (r.get("suppliers") or {}).get("name", "") } for r in rows])
def sellers() -> pd.DataFrame:
    return _frame([{ "id": r["id"], "Vendeur": r["name"], "Telephone": r.get("phone", ""), "Email": r.get("email", "") } for r in _data(_table("sellers").select("*").eq("active", True).order("name").execute())])
def suppliers() -> pd.DataFrame:
    return _frame([{ "id": r["id"], "Fournisseur": r["name"], "Contact": r.get("contact", ""), "Telephone": r.get("phone", ""), "Email": r.get("email", ""), "Adresse": r.get("address", "") } for r in _data(_table("suppliers").select("*").order("name").execute())])
def clients() -> pd.DataFrame:
    return _frame([{ "id": r["id"], "Client": r["name"], "Telephone": r.get("phone", ""), "Email": r.get("email", ""), "Adresse": r.get("address", "") } for r in _data(_table("clients").select("*").order("name").execute())])
def users() -> pd.DataFrame:
    rows = _data(_table("users").select("*,sellers(name)").eq("active", True).order("role").execute())
    return _frame([{ "id": r["id"], "Identifiant": r["username"], "Nom": r["display_name"], "Role": r["role"], "Vendeur": (r.get("sellers") or {}).get("name", "") } for r in rows])
def low_stock() -> pd.DataFrame:
    return _frame([{ "Produit": r["name"], "Stock": r["stock"], "Minimum": r["min_stock"] } for r in _data(_table("products").select("*").execute()) if int(r["stock"]) <= int(r["min_stock"])])


def save_sale(cart, seller_id, client_id, paid, method, discount):
    gross = sum(item["quantity"] * item["sale_price"] for item in cart); discount = max(0, min(discount, gross)); total = gross - discount
    for item in cart:
        product = _one("products", id=item["id"])
        if product is None or int(product["stock"]) < int(item["quantity"]): raise ValueError("Stock insuffisant.")
    sale = _data(_table("sales").insert({"seller_id": seller_id, "client_id": client_id, "total": total, "discount": discount, "paid": paid, "payment_method": method}).execute())[0]
    for item in cart:
        _table("sale_items").insert({"sale_id": sale["id"], "product_id": item["id"], "quantity": item["quantity"], "unit_price": item["sale_price"]}).execute()
        adjust_stock(item["id"], -int(item["quantity"]))
    return int(sale["id"]), gross, total


def add_expense(label, amount): _table("expenses").insert({"label": label, "amount": amount}).execute()


def register_purchase(product_id, quantity, unit_cost, supplier_name=""):
    if int(quantity) <= 0 or float(unit_cost) < 0:
        raise ValueError("Quantité ou prix d'achat invalide.")
    product = _one("products", id=product_id)
    if product is None:
        raise ValueError("Produit introuvable.")
    adjust_stock(product_id, int(quantity))
    _table("products").update({"purchase_price": float(unit_cost)}).eq("id", product_id).execute()
    label = f"Achat stock - {product['name']} x{int(quantity)}"
    if supplier_name:
        label += f" - {supplier_name}"
    add_expense(label, float(quantity) * float(unit_cost))


def client_history(client_id):
    rows = _data(_table("sales").select("id,created_at,total,paid,payment_method").eq("client_id", client_id).order("created_at", desc=True).execute())
    return _frame([{
        "Ticket": r["id"], "Date": r["created_at"], "Total": r["total"],
        "Paye": r["paid"], "Reste": max(0, float(r["total"]) - float(r["paid"])),
        "Paiement": r["payment_method"],
    } for r in rows])


def product_performance(start, end):
    sales = {r["id"]: r for r in _data(_table("sales").select("id,created_at").execute()) if start.isoformat() <= r["created_at"][:10] <= end.isoformat()}
    products = {r["id"]: r for r in _data(_table("products").select("id,name,purchase_price").execute())}
    totals = {}
    for item in _data(_table("sale_items").select("sale_id,product_id,quantity,unit_price").execute()):
        if item["sale_id"] not in sales:
            continue
        product = products.get(item["product_id"], {"name": "Produit supprimé", "purchase_price": 0})
        row = totals.setdefault(item["product_id"], {"Produit": product["name"], "Quantite": 0, "Chiffre": 0.0, "Benefice": 0.0})
        quantity = int(item["quantity"]); revenue = quantity * float(item["unit_price"])
        row["Quantite"] += quantity; row["Chiffre"] += revenue
        row["Benefice"] += revenue - quantity * float(product.get("purchase_price") or 0)
    return _frame(sorted(totals.values(), key=lambda r: r["Chiffre"], reverse=True))
def today_summary() -> pd.DataFrame:
    rows = _data(_table("sales").select("total,created_at").execute()); today = date.today().isoformat(); values = [float(r["total"]) for r in rows if r["created_at"].startswith(today)]
    return _frame([{ "sales": sum(values), "transactions": len(values) }])
def report(start, end) -> pd.DataFrame:
    rows = _data(_table("sales").select("*,sellers(name),clients(name)").order("created_at", desc=True).execute())
    return _frame([{ "Ticket": r["id"], "Date": r["created_at"], "Vendeur": (r.get("sellers") or {}).get("name", "Inconnu"), "Client": (r.get("clients") or {}).get("name", "Comptant"), "Total": r["total"], "Reduction": r["discount"], "Encaisse": r["paid"], "Paiement": r["payment_method"] } for r in rows if start.isoformat() <= r["created_at"][:10] <= end.isoformat()])
def expenses(start, end) -> pd.DataFrame:
    return _frame([{ "Date": r["created_at"], "Libelle": r["label"], "Montant": r["amount"] } for r in _data(_table("expenses").select("*").order("created_at", desc=True).execute()) if start.isoformat() <= r["created_at"][:10] <= end.isoformat()])


def sale_details(sale_id):
    sale = _one("sales", id=sale_id)
    if sale is None: return None
    products_by_id = {r["id"]: r["name"] for r in _data(_table("products").select("id,name").execute())}
    items = _data(_table("sale_items").select("*").eq("sale_id", sale_id).execute())
    return sale, _frame([{ "product_id": r["product_id"], "Produit": products_by_id.get(r["product_id"], "Produit supprimé"), "Quantite": r["quantity"], "Prix": r["unit_price"], "Total": r["quantity"] * r["unit_price"] } for r in items])
def update_sale(sale_id, client_id, paid, method, discount):
    details = sale_details(sale_id)
    if details is None: raise ValueError("Vente introuvable.")
    _, items = details; gross = float(items.Total.sum()); discount = max(0, min(float(discount), gross)); total = gross - discount
    _table("sales").update({"client_id": client_id, "paid": paid, "payment_method": method, "discount": discount, "total": total}).eq("id", sale_id).execute(); return gross, total
def delete_sale(sale_id):
    details = sale_details(sale_id)
    if details is None: raise ValueError("Vente introuvable.")
    items = _data(_table("sale_items").select("product_id,quantity").eq("sale_id", sale_id).execute())
    for item in items: adjust_stock(item["product_id"], int(item["quantity"]))
    _table("sale_items").delete().eq("sale_id", sale_id).execute(); _table("sales").delete().eq("id", sale_id).execute()


def return_sale_item(sale_id, product_id, quantity):
    item = _one("sale_items", sale_id=sale_id, product_id=product_id)
    if item is None or int(quantity) <= 0 or int(quantity) > int(item["quantity"]):
        raise ValueError("Quantité retournée invalide.")
    remaining = int(item["quantity"]) - int(quantity)
    if remaining:
        _table("sale_items").update({"quantity": remaining}).eq("id", item["id"]).execute()
    else:
        _table("sale_items").delete().eq("id", item["id"]).execute()
    adjust_stock(product_id, int(quantity))
    details = sale_details(sale_id)
    if details is None:
        raise ValueError("Vente introuvable.")
    sale, items = details
    gross = float(items.Total.sum()) if not items.empty else 0.0
    discount = min(float(sale.get("discount") or 0), gross)
    total = gross - discount
    paid = min(float(sale.get("paid") or 0), total)
    _table("sales").update({"total": total, "discount": discount, "paid": paid}).eq("id", sale_id).execute()
    return total
