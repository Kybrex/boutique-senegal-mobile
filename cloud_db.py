"""Implémentation Supabase de la couche de données Boutique Senegal."""
from __future__ import annotations

from datetime import date
import pandas as pd

from supabase_client import client, is_configured


def enabled() -> bool:
    return is_configured()


def _data(response) -> list[dict]:
    return response.data or []


def _frame(rows: list[dict], columns: list[str] | None = None) -> pd.DataFrame:
    """Create a DataFrame that keeps its schema even when Supabase returns no rows."""
    return pd.DataFrame(rows, columns=columns)


def _table(name: str):
    return client().table(name)


def _one(table_name: str, **filters) -> dict | None:
    """Return one row; table_name avoids collisions with a column named name."""
    request = _table(table_name).select("*")
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


def set_stock(product_id, stock):
    _table("products").update({"stock": stock}).eq("id", product_id).execute()
    if v2_ready():
        main = _one("stores", name="Boutique principale")
        if main: _table("store_stock").upsert({"store_id":main["id"],"product_id":product_id,"stock":stock}).execute()


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
    return _frame([{ "id": r["id"], "Produit": r["name"], "Categorie": r.get("category", ""), "Achat": r["purchase_price"], "Vente": r["sale_price"], "Stock": r["stock"], "Minimum": r["min_stock"], "Fournisseur": (r.get("suppliers") or {}).get("name", ""), "Code_barres": r.get("barcode", "") or "", "Photo": r.get("photo_url", "") or "" } for r in rows], ["id", "Produit", "Categorie", "Achat", "Vente", "Stock", "Minimum", "Fournisseur", "Code_barres", "Photo"])
def sellers() -> pd.DataFrame:
    return _frame([{ "id": r["id"], "Vendeur": r["name"], "Telephone": r.get("phone", ""), "Email": r.get("email", "") } for r in _data(_table("sellers").select("*").eq("active", True).order("name").execute())], ["id", "Vendeur", "Telephone", "Email"])
def suppliers() -> pd.DataFrame:
    return _frame([{ "id": r["id"], "Fournisseur": r["name"], "Contact": r.get("contact", ""), "Telephone": r.get("phone", ""), "Email": r.get("email", ""), "Adresse": r.get("address", "") } for r in _data(_table("suppliers").select("*").order("name").execute())], ["id", "Fournisseur", "Contact", "Telephone", "Email", "Adresse"])
def clients() -> pd.DataFrame:
    return _frame([{ "id": r["id"], "Client": r["name"], "Telephone": r.get("phone", ""), "Email": r.get("email", ""), "Adresse": r.get("address", "") } for r in _data(_table("clients").select("*").order("name").execute())], ["id", "Client", "Telephone", "Email", "Adresse"])
def users() -> pd.DataFrame:
    rows = _data(_table("users").select("*,sellers(name)").eq("active", True).order("role").execute())
    return _frame([{ "id": r["id"], "Identifiant": r["username"], "Nom": r["display_name"], "Role": r["role"], "Vendeur": (r.get("sellers") or {}).get("name", "") } for r in rows], ["id", "Identifiant", "Nom", "Role", "Vendeur"])
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


# Boutique Senegal V2
def v2_ready() -> bool:
    try:
        _table("shop_settings").select("id").limit(1).execute()
        return True
    except Exception:
        return False


def v2_error() -> str:
    try:
        _table("shop_settings").select("id").limit(1).execute()
        return ""
    except Exception as error:
        message = str(error).replace("SUPABASE_KEY", "clé Supabase")
        return message[:500]


def update_product_details(product_id, barcode, photo_url):
    _table("products").update({"barcode": barcode.strip() or None, "photo_url": photo_url.strip()}).eq("id", product_id).execute()


def find_product_by_barcode(barcode):
    row = _one("products", barcode=barcode.strip())
    if row is None: return None
    return {"id": row["id"], "Produit": row["name"], "Vente": row["sale_price"], "Stock": row["stock"]}


def add_credit_payment(client_id, sale_id, amount, method, user_id):
    sale = _one("sales", id=sale_id)
    if sale is None or sale.get("client_id") != client_id: raise ValueError("Vente à crédit introuvable.")
    remaining = max(0, float(sale["total"]) - float(sale["paid"]))
    if amount <= 0 or amount > remaining: raise ValueError("Le paiement dépasse le solde restant.")
    _table("sales").update({"paid": float(sale["paid"]) + float(amount)}).eq("id", sale_id).execute()
    _table("credit_payments").insert({"client_id":client_id,"sale_id":sale_id,"amount":amount,"payment_method":method,"recorded_by":user_id}).execute()


def credit_payments(client_id):
    rows = _data(_table("credit_payments").select("*,users(display_name)").eq("client_id",client_id).order("created_at",desc=True).execute())
    return _frame([{"Date":r["created_at"],"Ticket":r.get("sale_id"),"Montant":r["amount"],"Paiement":r["payment_method"],"Enregistre_par":(r.get("users") or {}).get("display_name","")} for r in rows], ["Date","Ticket","Montant","Paiement","Enregistre_par"])


def cash_summary(day, seller_id=None):
    rows = _data(_table("sales").select("seller_id,paid,payment_method,created_at").execute())
    totals = {}
    for row in rows:
        if row["created_at"][:10] != day.isoformat() or (seller_id is not None and row.get("seller_id") != seller_id): continue
        item = totals.setdefault(row["payment_method"], {"Paiement":row["payment_method"],"Transactions":0,"Montant":0.0})
        item["Transactions"] += 1; item["Montant"] += float(row["paid"])
    return _frame(list(totals.values()), ["Paiement","Transactions","Montant"])


def close_cash(day, seller_id, counted, notes, user_id):
    summary = cash_summary(day,seller_id); expected=float(summary.loc[summary.Paiement=="Especes","Montant"].sum()) if not summary.empty else 0.0
    _table("cash_closings").insert({"closing_date":day.isoformat(),"seller_id":seller_id,"expected_cash":expected,"counted_cash":counted,"difference":counted-expected,"notes":notes.strip(),"closed_by":user_id}).execute()


def cash_closings():
    rows=_data(_table("cash_closings").select("*,sellers(name)").order("created_at",desc=True).limit(100).execute())
    return _frame([{"Date":r["closing_date"],"Vendeur":(r.get("sellers") or {}).get("name","Tous"),"Attendu":r["expected_cash"],"Compte":r["counted_cash"],"Ecart":r["difference"],"Notes":r.get("notes","")} for r in rows], ["Date","Vendeur","Attendu","Compte","Ecart","Notes"])


def log_action(user_id, action, details=""):
    _table("activity_logs").insert({"user_id":user_id,"action":action,"details":details[:500]}).execute()


def audit_logs():
    rows=_data(_table("activity_logs").select("*,users(display_name)").order("created_at",desc=True).limit(300).execute())
    return _frame([{"Date":r["created_at"],"Utilisateur":(r.get("users") or {}).get("display_name","Systeme"),"Action":r["action"],"Details":r.get("details","")} for r in rows], ["Date","Utilisateur","Action","Details"])


def set_user_active(user_id, active): _table("users").update({"active":active}).eq("id",user_id).neq("role","admin").execute()
def reset_user_password(user_id, password_hash): _table("users").update({"password_hash":password_hash}).eq("id",user_id).execute()
def all_users():
    rows=_data(_table("users").select("*").order("role").execute())
    return _frame([{"id":r["id"],"Identifiant":r["username"],"Nom":r["display_name"],"Role":r["role"],"Actif":r["active"]} for r in rows], ["id","Identifiant","Nom","Role","Actif"])


def inventory_snapshot():
    rows=_data(_table("products").select("id,name,stock,barcode").order("name").execute())
    return _frame([{"id":r["id"],"Produit":r["name"],"Stock":r["stock"],"Code_barres":r.get("barcode","")} for r in rows], ["id","Produit","Stock","Code_barres"])
def save_inventory_count(product_id, counted, user_id, notes=""):
    product=_one("products",id=product_id)
    if product is None or counted < 0: raise ValueError("Comptage invalide.")
    expected=int(product["stock"]); set_stock(product_id,counted)
    _table("inventory_counts").insert({"product_id":product_id,"expected_stock":expected,"counted_stock":counted,"difference":counted-expected,"counted_by":user_id,"notes":notes.strip()}).execute()
def inventory_history():
    rows=_data(_table("inventory_counts").select("*,products(name)").order("created_at",desc=True).limit(200).execute())
    return _frame([{"Date":r["created_at"],"Produit":(r.get("products") or {}).get("name",""),"Stock_systeme":r["expected_stock"],"Stock_compte":r["counted_stock"],"Ecart":r["difference"],"Notes":r.get("notes","")} for r in rows], ["Date","Produit","Stock_systeme","Stock_compte","Ecart","Notes"])


def stores():
    rows=_data(_table("stores").select("*").eq("active",True).order("name").execute())
    return _frame([{"id":r["id"],"Boutique":r["name"],"Adresse":r.get("address", ""),"Telephone":r.get("phone","")} for r in rows], ["id","Boutique","Adresse","Telephone"])
def add_store(name,address,phone): _table("stores").insert({"name":name.strip(),"address":address.strip(),"phone":phone.strip()}).execute()
def store_inventory(store_id):
    products=_data(_table("products").select("id,name,stock").order("name").execute()); stocks={r["product_id"]:r["stock"] for r in _data(_table("store_stock").select("*").eq("store_id",store_id).execute())}; main=_one("stores",name="Boutique principale")
    return _frame([{"id":p["id"],"Produit":p["name"],"Stock":stocks.get(p["id"],p["stock"] if main and store_id==main["id"] else 0)} for p in products], ["id","Produit","Stock"])
def transfer_stock(product_id, from_store, to_store, quantity, user_id, notes=""):
    if from_store==to_store or quantity<=0: raise ValueError("Transfert invalide.")
    source=store_inventory(from_store); target=store_inventory(to_store)
    source_stock=int(source.loc[source.id==product_id,"Stock"].iloc[0]); target_stock=int(target.loc[target.id==product_id,"Stock"].iloc[0])
    if source_stock<quantity: raise ValueError("Stock insuffisant dans la boutique source.")
    for store,value in ((from_store,source_stock-quantity),(to_store,target_stock+quantity)):
        _table("store_stock").upsert({"store_id":store,"product_id":product_id,"stock":value}).execute()
        main=_one("stores",name="Boutique principale")
        if main and store==main["id"]: set_stock(product_id,value)
    _table("stock_transfers").insert({"product_id":product_id,"from_store_id":from_store,"to_store_id":to_store,"quantity":quantity,"transferred_by":user_id,"notes":notes.strip()}).execute()
def transfer_history():
    rows=_data(_table("stock_transfers").select("*,products(name)").order("created_at",desc=True).limit(200).execute()); stores_by_id={r["id"]:r["name"] for r in _data(_table("stores").select("id,name").execute())}
    return _frame([{"Date":r["created_at"],"Produit":(r.get("products") or {}).get("name",""),"Source":stores_by_id.get(r["from_store_id"],""),"Destination":stores_by_id.get(r["to_store_id"],""),"Quantite":r["quantity"],"Notes":r.get("notes","")} for r in rows], ["Date","Produit","Source","Destination","Quantite","Notes"])


def get_settings():
    return _one("shop_settings",id=1) or {"shop_name":"Boutique Senegal","phone":"","address":"","logo_url":"","receipt_footer":"Merci pour votre achat !"}
def update_settings(shop_name,phone,address,logo_url,footer):
    _table("shop_settings").upsert({"id":1,"shop_name":shop_name.strip(),"phone":phone.strip(),"address":address.strip(),"logo_url":logo_url.strip(),"receipt_footer":footer.strip()}).execute()
def dashboard(start,end):
    sales_df=report(start,end); expense_df=expenses(start,end); perf=product_performance(start,end)
    revenue=float(sales_df.Total.sum()) if not sales_df.empty else 0.0; spent=float(expense_df.Montant.sum()) if not expense_df.empty else 0.0; profit=float(perf.Benefice.sum()) if not perf.empty else 0.0
    all_sales=_data(_table("sales").select("total,paid").execute()); debt=sum(max(0,float(r["total"])-float(r["paid"])) for r in all_sales)
    return {"sales":revenue,"expenses":spent,"gross_profit":profit,"net":revenue-spent,"debt":debt,"transactions":len(sales_df),"performance":perf}
