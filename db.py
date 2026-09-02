"""SQLite storage and secure local accounts for Boutique Senegal."""
from __future__ import annotations
from datetime import date
from pathlib import Path
import hashlib
import hmac
import os
import sqlite3
import pandas as pd

DB_PATH = Path(__file__).parent / "boutique.db"
def connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row; return conn
def _column(conn: sqlite3.Connection, table: str, name: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if name not in columns: conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
def init_db() -> None:
    with connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, category TEXT, purchase_price REAL DEFAULT 0, sale_price REAL NOT NULL, stock INTEGER NOT NULL DEFAULT 0, min_stock INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS sellers (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, phone TEXT, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS suppliers (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, contact TEXT, phone TEXT, address TEXT);
        CREATE TABLE IF NOT EXISTS clients (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, phone TEXT, address TEXT);
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL, seller_id INTEGER, active INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS sales (id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, seller_id INTEGER, total REAL NOT NULL, paid REAL NOT NULL, payment_method TEXT NOT NULL, FOREIGN KEY(seller_id) REFERENCES sellers(id));
        CREATE TABLE IF NOT EXISTS sale_items (id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL, product_id INTEGER NOT NULL, quantity INTEGER NOT NULL, unit_price REAL NOT NULL, FOREIGN KEY(sale_id) REFERENCES sales(id), FOREIGN KEY(product_id) REFERENCES products(id));
        CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, label TEXT NOT NULL, amount REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS credit_payments (id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, client_id INTEGER NOT NULL, sale_id INTEGER, amount REAL NOT NULL, payment_method TEXT NOT NULL, recorded_by INTEGER);
        CREATE TABLE IF NOT EXISTS cash_closings (id INTEGER PRIMARY KEY, closing_date TEXT NOT NULL, seller_id INTEGER, expected_cash REAL NOT NULL DEFAULT 0, counted_cash REAL NOT NULL DEFAULT 0, difference REAL NOT NULL DEFAULT 0, notes TEXT DEFAULT '', closed_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS activity_logs (id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, user_id INTEGER, action TEXT NOT NULL, details TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS inventory_counts (id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, product_id INTEGER NOT NULL, expected_stock INTEGER NOT NULL, counted_stock INTEGER NOT NULL, difference INTEGER NOT NULL, counted_by INTEGER, notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS stores (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, address TEXT DEFAULT '', phone TEXT DEFAULT '', active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS store_stock (store_id INTEGER NOT NULL, product_id INTEGER NOT NULL, stock INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(store_id,product_id));
        CREATE TABLE IF NOT EXISTS stock_transfers (id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP, product_id INTEGER NOT NULL, from_store_id INTEGER NOT NULL, to_store_id INTEGER NOT NULL, quantity INTEGER NOT NULL, transferred_by INTEGER, notes TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS shop_settings (id INTEGER PRIMARY KEY CHECK(id=1), shop_name TEXT NOT NULL DEFAULT 'Boutique Senegal', phone TEXT DEFAULT '', address TEXT DEFAULT '', logo_url TEXT DEFAULT '', receipt_footer TEXT DEFAULT 'Merci pour votre achat !', currency TEXT DEFAULT 'FCFA');
        INSERT OR IGNORE INTO stores(id,name) VALUES(1,'Boutique principale');
        INSERT OR IGNORE INTO shop_settings(id) VALUES(1);
        """)
        _column(conn, "products", "supplier_id", "INTEGER")
        _column(conn, "sales", "client_id", "INTEGER")
        _column(conn, "sales", "discount", "REAL NOT NULL DEFAULT 0")
        _column(conn, "sellers", "email", "TEXT")
        _column(conn, "suppliers", "email", "TEXT")
        _column(conn, "clients", "email", "TEXT")
        _column(conn, "products", "barcode", "TEXT")
        _column(conn, "products", "photo_url", "TEXT DEFAULT ''")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS products_barcode_unique ON products(barcode) WHERE barcode IS NOT NULL AND barcode<>''")
        conn.commit()
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    with connection() as conn: return pd.read_sql_query(sql, conn, params=params)
def execute(sql: str, params: tuple = ()) -> None:
    with connection() as conn: conn.execute(sql, params); conn.commit()
def password_hash(password: str) -> str:
    salt = os.urandom(16); digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}${digest.hex()}"
def valid_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1); test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 200_000)
        return hmac.compare_digest(test.hex(), digest_hex)
    except (ValueError, AttributeError): return False
def user_count() -> int: return int(query("SELECT COUNT(*) AS c FROM users").iloc[0].c)
def create_user(username: str, display_name: str, password: str, role: str, seller_id: int | None = None) -> None:
    execute("INSERT INTO users(username,display_name,password_hash,role,seller_id) VALUES(?,?,?,?,?)", (username.strip().lower(), display_name.strip(), password_hash(password), role, seller_id))
def authenticate(username: str, password: str) -> dict | None:
    users = query("SELECT id,username,display_name,password_hash,role,seller_id FROM users WHERE username=? AND active=1", (username.strip().lower(),))
    if users.empty or not valid_password(password, users.iloc[0].password_hash): return None
    return users.drop(columns="password_hash").iloc[0].to_dict()
def add_product(name: str, category: str, purchase: float, sale: float, stock: int, minimum: int, supplier_id: int | None) -> None:
    execute("INSERT INTO products(name,category,purchase_price,sale_price,stock,min_stock,supplier_id) VALUES(?,?,?,?,?,?,?)", (name.strip(), category.strip(), purchase, sale, stock, minimum, supplier_id))
def set_stock(product_id: int, stock: int) -> None:
    with connection() as conn:
        conn.execute("UPDATE products SET stock=? WHERE id=?", (stock, product_id))
        conn.execute("INSERT INTO store_stock(store_id,product_id,stock) VALUES(1,?,?) ON CONFLICT(store_id,product_id) DO UPDATE SET stock=excluded.stock", (product_id,stock)); conn.commit()
def adjust_stock(product_id: int, adjustment: int) -> None:
    with connection() as conn:
        current = conn.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()
        if current is None: raise ValueError("Produit introuvable")
        new_stock = current["stock"] + adjustment
        if new_stock < 0: raise ValueError("Le stock ne peut pas etre negatif")
        conn.execute("UPDATE products SET stock=? WHERE id=?", (new_stock, product_id))
        conn.execute("INSERT INTO store_stock(store_id,product_id,stock) VALUES(1,?,?) ON CONFLICT(store_id,product_id) DO UPDATE SET stock=excluded.stock", (product_id,new_stock)); conn.commit()
def add_seller(name: str, phone: str, email: str) -> None: execute("INSERT INTO sellers(name,phone,email) VALUES(?,?,?)", (name.strip(), phone.strip(), email.strip().lower()))
def create_seller_with_user(name: str, phone: str, email: str, username: str, password: str) -> None:
    with connection() as conn:
        cursor = conn.execute("INSERT INTO sellers(name,phone,email) VALUES(?,?,?)", (name.strip(), phone.strip(), email.strip().lower()))
        conn.execute("INSERT INTO users(username,display_name,password_hash,role,seller_id) VALUES(?,?,?,?,?)", (username.strip().lower(), name.strip(), password_hash(password), "seller", cursor.lastrowid))
        conn.commit()
def add_supplier(name: str, contact: str, phone: str, email: str, address: str) -> None: execute("INSERT INTO suppliers(name,contact,phone,email,address) VALUES(?,?,?,?,?)", (name.strip(), contact.strip(), phone.strip(), email.strip().lower(), address.strip()))
def add_client(name: str, phone: str, email: str, address: str) -> None: execute("INSERT INTO clients(name,phone,email,address) VALUES(?,?,?,?)", (name.strip(), phone.strip(), email.strip().lower(), address.strip()))
def save_sale(cart: list[dict], seller_id: int, client_id: int | None, paid: float, method: str, discount: float) -> tuple[int, float, float]:
    gross = sum(item["quantity"] * item["sale_price"] for item in cart); discount = max(0, min(discount, gross)); total = gross-discount
    with connection() as conn:
        cursor = conn.execute("INSERT INTO sales(seller_id,client_id,total,discount,paid,payment_method) VALUES(?,?,?,?,?,?)", (seller_id, client_id, total, discount, paid, method)); sale_id = cursor.lastrowid
        for item in cart:
            conn.execute("INSERT INTO sale_items(sale_id,product_id,quantity,unit_price) VALUES(?,?,?,?)", (sale_id, item["id"], item["quantity"], item["sale_price"]))
            conn.execute("UPDATE products SET stock=stock-? WHERE id=? AND stock>=?", (item["quantity"], item["id"], item["quantity"]))
            current = conn.execute("SELECT stock FROM products WHERE id=?", (item["id"],)).fetchone()["stock"]
            conn.execute("INSERT INTO store_stock(store_id,product_id,stock) VALUES(1,?,?) ON CONFLICT(store_id,product_id) DO UPDATE SET stock=excluded.stock", (item["id"],current))
        conn.commit()
    return sale_id, gross, total
def sale_details(sale_id: int) -> tuple[dict, pd.DataFrame] | None:
    sale = query("SELECT s.id,s.created_at,s.client_id,s.total,s.discount,s.paid,s.payment_method,COALESCE(c.name,'Comptant') AS client FROM sales s LEFT JOIN clients c ON c.id=s.client_id WHERE s.id=?", (sale_id,))
    if sale.empty:
        return None
    items = query("SELECT si.product_id,p.name AS Produit,si.quantity AS Quantite,si.unit_price AS Prix,si.quantity*si.unit_price AS Total FROM sale_items si LEFT JOIN products p ON p.id=si.product_id WHERE si.sale_id=? ORDER BY si.id", (sale_id,))
    return sale.iloc[0].to_dict(), items
def update_sale(sale_id: int, client_id: int | None, paid: float, method: str, discount: float) -> tuple[float, float]:
    if paid < 0:
        raise ValueError("Le montant encaissé ne peut pas être négatif.")
    with connection() as conn:
        exists = conn.execute("SELECT id FROM sales WHERE id=?", (sale_id,)).fetchone()
        if exists is None:
            raise ValueError("Vente introuvable.")
        gross = float(conn.execute("SELECT COALESCE(SUM(quantity*unit_price),0) AS gross FROM sale_items WHERE sale_id=?", (sale_id,)).fetchone()["gross"])
        discount = max(0, min(float(discount), gross))
        total = gross - discount
        conn.execute("UPDATE sales SET client_id=?,paid=?,payment_method=?,discount=?,total=? WHERE id=?", (client_id, paid, method, discount, total, sale_id))
        conn.commit()
    return gross, total
def delete_sale(sale_id: int) -> None:
    with connection() as conn:
        items = conn.execute("SELECT product_id,quantity FROM sale_items WHERE sale_id=?", (sale_id,)).fetchall()
        if conn.execute("SELECT id FROM sales WHERE id=?", (sale_id,)).fetchone() is None:
            raise ValueError("Vente introuvable.")
        for item in items:
            conn.execute("UPDATE products SET stock=stock+? WHERE id=?", (item["quantity"], item["product_id"]))
            current = conn.execute("SELECT stock FROM products WHERE id=?", (item["product_id"],)).fetchone()["stock"]
            conn.execute("INSERT INTO store_stock(store_id,product_id,stock) VALUES(1,?,?) ON CONFLICT(store_id,product_id) DO UPDATE SET stock=excluded.stock", (item["product_id"],current))
        conn.execute("DELETE FROM sale_items WHERE sale_id=?", (sale_id,))
        conn.execute("DELETE FROM sales WHERE id=?", (sale_id,))
        conn.commit()
def return_sale_item(sale_id: int, product_id: int, quantity: int) -> float:
    with connection() as conn:
        item = conn.execute("SELECT id,quantity FROM sale_items WHERE sale_id=? AND product_id=?", (sale_id, product_id)).fetchone()
        if item is None or quantity <= 0 or quantity > item["quantity"]: raise ValueError("Quantité retournée invalide.")
        remaining = item["quantity"] - quantity
        if remaining: conn.execute("UPDATE sale_items SET quantity=? WHERE id=?", (remaining, item["id"]))
        else: conn.execute("DELETE FROM sale_items WHERE id=?", (item["id"],))
        conn.execute("UPDATE products SET stock=stock+? WHERE id=?", (quantity, product_id))
        current = conn.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()["stock"]
        conn.execute("INSERT INTO store_stock(store_id,product_id,stock) VALUES(1,?,?) ON CONFLICT(store_id,product_id) DO UPDATE SET stock=excluded.stock", (product_id,current))
        gross = float(conn.execute("SELECT COALESCE(SUM(quantity*unit_price),0) AS gross FROM sale_items WHERE sale_id=?", (sale_id,)).fetchone()["gross"])
        sale = conn.execute("SELECT discount,paid FROM sales WHERE id=?", (sale_id,)).fetchone()
        discount = min(float(sale["discount"]), gross); total = gross-discount; paid = min(float(sale["paid"]), total)
        conn.execute("UPDATE sales SET total=?,discount=?,paid=? WHERE id=?", (total, discount, paid, sale_id)); conn.commit()
        return total
def add_expense(label: str, amount: float) -> None: execute("INSERT INTO expenses(label,amount) VALUES(?,?)", (label.strip(), amount))
def register_purchase(product_id: int, quantity: int, unit_cost: float, supplier_name: str = "") -> None:
    if quantity <= 0 or unit_cost < 0: raise ValueError("Quantité ou prix d'achat invalide.")
    with connection() as conn:
        product = conn.execute("SELECT name FROM products WHERE id=?", (product_id,)).fetchone()
        if product is None: raise ValueError("Produit introuvable.")
        conn.execute("UPDATE products SET stock=stock+?,purchase_price=? WHERE id=?", (quantity, unit_cost, product_id))
        current = conn.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()["stock"]
        conn.execute("INSERT INTO store_stock(store_id,product_id,stock) VALUES(1,?,?) ON CONFLICT(store_id,product_id) DO UPDATE SET stock=excluded.stock", (product_id,current))
        label = f"Achat stock - {product['name']} x{quantity}" + (f" - {supplier_name}" if supplier_name else "")
        conn.execute("INSERT INTO expenses(label,amount) VALUES(?,?)", (label, quantity*unit_cost)); conn.commit()
def client_history(client_id: int) -> pd.DataFrame:
    return query("SELECT id AS Ticket,created_at AS Date,total AS Total,paid AS Paye,MAX(total-paid,0) AS Reste,payment_method AS Paiement FROM sales WHERE client_id=? ORDER BY created_at DESC", (client_id,))
def product_performance(start: date, end: date) -> pd.DataFrame:
    return query("SELECT p.name AS Produit,SUM(si.quantity) AS Quantite,SUM(si.quantity*si.unit_price) AS Chiffre,SUM(si.quantity*(si.unit_price-p.purchase_price)) AS Benefice FROM sale_items si JOIN sales s ON s.id=si.sale_id LEFT JOIN products p ON p.id=si.product_id WHERE date(s.created_at) BETWEEN ? AND ? GROUP BY si.product_id,p.name ORDER BY Chiffre DESC", (start.isoformat(), end.isoformat()))
def products() -> pd.DataFrame: return query("SELECT p.id,p.name AS Produit,p.category AS Categorie,p.purchase_price AS Achat,p.sale_price AS Vente,p.stock AS Stock,p.min_stock AS Minimum,COALESCE(s.name,'') AS Fournisseur,COALESCE(p.barcode,'') AS Code_barres,COALESCE(p.photo_url,'') AS Photo FROM products p LEFT JOIN suppliers s ON s.id=p.supplier_id ORDER BY p.name")
def sellers() -> pd.DataFrame: return query("SELECT id,name AS Vendeur,phone AS Telephone,email AS Email FROM sellers WHERE active=1 ORDER BY name")
def suppliers() -> pd.DataFrame: return query("SELECT id,name AS Fournisseur,contact AS Contact,phone AS Telephone,email AS Email,address AS Adresse FROM suppliers ORDER BY name")
def clients() -> pd.DataFrame: return query("SELECT id,name AS Client,phone AS Telephone,email AS Email,address AS Adresse FROM clients ORDER BY name")
def users() -> pd.DataFrame: return query("SELECT u.id,u.username AS Identifiant,u.display_name AS Nom,u.role AS Role,COALESCE(s.name,'') AS Vendeur FROM users u LEFT JOIN sellers s ON s.id=u.seller_id WHERE u.active=1 ORDER BY u.role,u.display_name")
def low_stock() -> pd.DataFrame: return query("SELECT name AS Produit,stock AS Stock,min_stock AS Minimum FROM products WHERE stock<=min_stock ORDER BY stock")
def today_summary() -> pd.DataFrame: return query("SELECT COALESCE(SUM(total),0) AS sales, COUNT(*) AS transactions FROM sales WHERE date(created_at)=?", (date.today().isoformat(),))
def report(start: date, end: date) -> pd.DataFrame: return query("SELECT s.id AS Ticket,s.created_at AS Date,COALESCE(v.name,'Inconnu') AS Vendeur,COALESCE(c.name,'Comptant') AS Client,s.total AS Total,s.discount AS Reduction,s.paid AS Encaisse,s.payment_method AS Paiement FROM sales s LEFT JOIN sellers v ON v.id=s.seller_id LEFT JOIN clients c ON c.id=s.client_id WHERE date(s.created_at) BETWEEN ? AND ? ORDER BY s.created_at DESC", (start.isoformat(), end.isoformat()))
def expenses(start: date, end: date) -> pd.DataFrame: return query("SELECT created_at AS Date,label AS Libelle,amount AS Montant FROM expenses WHERE date(created_at) BETWEEN ? AND ? ORDER BY created_at DESC", (start.isoformat(), end.isoformat()))

# Boutique Senegal V2
def v2_ready() -> bool: return True
def update_product_details(product_id: int, barcode: str, photo_url: str) -> None:
    execute("UPDATE products SET barcode=?,photo_url=? WHERE id=?", (barcode.strip() or None, photo_url.strip(), product_id))
def find_product_by_barcode(barcode: str) -> dict | None:
    rows = query("SELECT id,name AS Produit,sale_price AS Vente,stock AS Stock FROM products WHERE barcode=?", (barcode.strip(),))
    return None if rows.empty else rows.iloc[0].to_dict()
def add_credit_payment(client_id: int, sale_id: int, amount: float, method: str, user_id: int) -> None:
    if amount <= 0: raise ValueError("Le montant doit être positif.")
    with connection() as conn:
        sale = conn.execute("SELECT total,paid,client_id FROM sales WHERE id=?", (sale_id,)).fetchone()
        if sale is None or sale["client_id"] != client_id: raise ValueError("Vente à crédit introuvable.")
        remaining = max(0, float(sale["total"])-float(sale["paid"]))
        if amount > remaining: raise ValueError("Le paiement dépasse le solde restant.")
        conn.execute("UPDATE sales SET paid=paid+? WHERE id=?", (amount, sale_id))
        conn.execute("INSERT INTO credit_payments(client_id,sale_id,amount,payment_method,recorded_by) VALUES(?,?,?,?,?)", (client_id,sale_id,amount,method,user_id)); conn.commit()
def credit_payments(client_id: int) -> pd.DataFrame:
    return query("SELECT cp.created_at AS Date,cp.sale_id AS Ticket,cp.amount AS Montant,cp.payment_method AS Paiement,COALESCE(u.display_name,'') AS Enregistre_par FROM credit_payments cp LEFT JOIN users u ON u.id=cp.recorded_by WHERE cp.client_id=? ORDER BY cp.created_at DESC", (client_id,))
def cash_summary(day: date, seller_id: int | None = None) -> pd.DataFrame:
    sql = "SELECT payment_method AS Paiement,COUNT(*) AS Transactions,SUM(paid) AS Montant FROM sales WHERE date(created_at)=?"
    params: tuple = (day.isoformat(),)
    if seller_id is not None: sql += " AND seller_id=?"; params += (seller_id,)
    return query(sql+" GROUP BY payment_method ORDER BY payment_method", params)
def close_cash(day: date, seller_id: int | None, counted: float, notes: str, user_id: int) -> None:
    summary = cash_summary(day, seller_id); expected = float(summary.loc[summary.Paiement == "Especes", "Montant"].sum()) if not summary.empty else 0.0
    execute("INSERT INTO cash_closings(closing_date,seller_id,expected_cash,counted_cash,difference,notes,closed_by) VALUES(?,?,?,?,?,?,?)", (day.isoformat(),seller_id,expected,counted,counted-expected,notes.strip(),user_id))
def cash_closings() -> pd.DataFrame:
    return query("SELECT c.closing_date AS Date,COALESCE(s.name,'Tous') AS Vendeur,c.expected_cash AS Attendu,c.counted_cash AS Compte,c.difference AS Ecart,c.notes AS Notes FROM cash_closings c LEFT JOIN sellers s ON s.id=c.seller_id ORDER BY c.created_at DESC LIMIT 100")
def log_action(user_id: int | None, action: str, details: str = "") -> None:
    execute("INSERT INTO activity_logs(user_id,action,details) VALUES(?,?,?)", (user_id,action,details[:500]))
def audit_logs() -> pd.DataFrame:
    return query("SELECT l.created_at AS Date,COALESCE(u.display_name,'Systeme') AS Utilisateur,l.action AS Action,l.details AS Details FROM activity_logs l LEFT JOIN users u ON u.id=l.user_id ORDER BY l.created_at DESC LIMIT 300")
def set_user_active(user_id: int, active: bool) -> None: execute("UPDATE users SET active=? WHERE id=? AND role<>'admin'", (int(active),user_id))
def reset_user_password(user_id: int, password: str) -> None: execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash(password),user_id))
def all_users() -> pd.DataFrame: return query("SELECT id,username AS Identifiant,display_name AS Nom,role AS Role,active AS Actif FROM users ORDER BY role,display_name")
def inventory_snapshot() -> pd.DataFrame: return query("SELECT id,name AS Produit,stock AS Stock,barcode AS Code_barres FROM products ORDER BY name")
def save_inventory_count(product_id: int, counted: int, user_id: int, notes: str = "") -> None:
    if counted < 0: raise ValueError("Le stock compté ne peut pas être négatif.")
    with connection() as conn:
        row = conn.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()
        if row is None: raise ValueError("Produit introuvable.")
        expected = int(row["stock"]); difference = counted-expected
        conn.execute("UPDATE products SET stock=? WHERE id=?", (counted,product_id))
        conn.execute("INSERT INTO store_stock(store_id,product_id,stock) VALUES(1,?,?) ON CONFLICT(store_id,product_id) DO UPDATE SET stock=excluded.stock", (product_id,counted))
        conn.execute("INSERT INTO inventory_counts(product_id,expected_stock,counted_stock,difference,counted_by,notes) VALUES(?,?,?,?,?,?)", (product_id,expected,counted,difference,user_id,notes.strip())); conn.commit()
def inventory_history() -> pd.DataFrame:
    return query("SELECT i.created_at AS Date,p.name AS Produit,i.expected_stock AS Stock_systeme,i.counted_stock AS Stock_compte,i.difference AS Ecart,i.notes AS Notes FROM inventory_counts i LEFT JOIN products p ON p.id=i.product_id ORDER BY i.created_at DESC LIMIT 200")
def stores() -> pd.DataFrame: return query("SELECT id,name AS Boutique,address AS Adresse,phone AS Telephone FROM stores WHERE active=1 ORDER BY name")
def add_store(name: str, address: str, phone: str) -> None: execute("INSERT INTO stores(name,address,phone) VALUES(?,?,?)", (name.strip(),address.strip(),phone.strip()))
def store_inventory(store_id: int) -> pd.DataFrame:
    return query("SELECT p.id,p.name AS Produit,COALESCE(ss.stock,CASE WHEN ?=1 THEN p.stock ELSE 0 END) AS Stock FROM products p LEFT JOIN store_stock ss ON ss.product_id=p.id AND ss.store_id=? ORDER BY p.name", (store_id,store_id))
def transfer_stock(product_id: int, from_store: int, to_store: int, quantity: int, user_id: int, notes: str = "") -> None:
    if from_store == to_store or quantity <= 0: raise ValueError("Transfert invalide.")
    with connection() as conn:
        def current(store: int) -> int:
            row = conn.execute("SELECT stock FROM store_stock WHERE store_id=? AND product_id=?", (store,product_id)).fetchone()
            if row is not None: return int(row["stock"])
            return int(conn.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()["stock"]) if store == 1 else 0
        source = current(from_store)
        if source < quantity: raise ValueError("Stock insuffisant dans la boutique source.")
        for store, value in ((from_store,source-quantity),(to_store,current(to_store)+quantity)):
            conn.execute("INSERT INTO store_stock(store_id,product_id,stock) VALUES(?,?,?) ON CONFLICT(store_id,product_id) DO UPDATE SET stock=excluded.stock", (store,product_id,value))
            if store == 1: conn.execute("UPDATE products SET stock=? WHERE id=?", (value,product_id))
        conn.execute("INSERT INTO stock_transfers(product_id,from_store_id,to_store_id,quantity,transferred_by,notes) VALUES(?,?,?,?,?,?)", (product_id,from_store,to_store,quantity,user_id,notes.strip())); conn.commit()
def transfer_history() -> pd.DataFrame:
    return query("SELECT t.created_at AS Date,p.name AS Produit,a.name AS Source,b.name AS Destination,t.quantity AS Quantite,t.notes AS Notes FROM stock_transfers t JOIN products p ON p.id=t.product_id JOIN stores a ON a.id=t.from_store_id JOIN stores b ON b.id=t.to_store_id ORDER BY t.created_at DESC LIMIT 200")
def get_settings() -> dict: return query("SELECT * FROM shop_settings WHERE id=1").iloc[0].to_dict()
def update_settings(shop_name: str, phone: str, address: str, logo_url: str, footer: str) -> None:
    execute("UPDATE shop_settings SET shop_name=?,phone=?,address=?,logo_url=?,receipt_footer=? WHERE id=1", (shop_name.strip(),phone.strip(),address.strip(),logo_url.strip(),footer.strip()))
def dashboard(start: date, end: date) -> dict:
    sales_df=report(start,end); expense_df=expenses(start,end); perf=product_performance(start,end)
    revenue=float(sales_df.Total.sum()) if not sales_df.empty else 0.0; spent=float(expense_df.Montant.sum()) if not expense_df.empty else 0.0
    profit=float(perf.Benefice.sum()) if not perf.empty else 0.0
    debt=float(query("SELECT COALESCE(SUM(MAX(total-paid,0)),0) AS d FROM sales").iloc[0].d)
    return {"sales":revenue,"expenses":spent,"gross_profit":profit,"net":revenue-spent,"debt":debt,"transactions":len(sales_df),"performance":perf}

# Sur Streamlit Cloud, les mêmes fonctions utilisent Supabase. En local, SQLite
# reste disponible sans configuration supplémentaire.
try:
    import cloud_db as _cloud
    if _cloud.enabled():
        def init_db() -> None: pass
        user_count = _cloud.user_count
        def create_user(username, display_name, password, role, seller_id=None): _cloud.create_user(username.strip().lower(), display_name.strip(), password_hash(password), role, seller_id)
        def authenticate(username, password):
            record = _cloud.authenticate(username.strip().lower())
            if record is None or not valid_password(password, record["password_hash"]): return None
            record.pop("password_hash", None); return record
        def add_product(name, category, purchase, sale, stock, minimum, supplier_id): _cloud.add_product(name.strip(), category.strip(), purchase, sale, stock, minimum, supplier_id)
        set_stock = _cloud.set_stock; adjust_stock = _cloud.adjust_stock
        def add_seller(name, phone, email): _cloud.add_seller(name.strip(), phone.strip(), email.strip().lower())
        def create_seller_with_user(name, phone, email, username, password): _cloud.create_seller_with_user(name.strip(), phone.strip(), email.strip().lower(), username.strip().lower(), password_hash(password))
        def add_supplier(name, contact, phone, email, address): _cloud.add_supplier(name.strip(), contact.strip(), phone.strip(), email.strip().lower(), address.strip())
        def add_client(name, phone, email, address): _cloud.add_client(name.strip(), phone.strip(), email.strip().lower(), address.strip())
        save_sale = _cloud.save_sale; add_expense = _cloud.add_expense
        products = _cloud.products; sellers = _cloud.sellers; suppliers = _cloud.suppliers; clients = _cloud.clients; users = _cloud.users; low_stock = _cloud.low_stock
        today_summary = _cloud.today_summary; report = _cloud.report; expenses = _cloud.expenses
        sale_details = _cloud.sale_details; update_sale = _cloud.update_sale; delete_sale = _cloud.delete_sale
        register_purchase = _cloud.register_purchase; client_history = _cloud.client_history
        product_performance = _cloud.product_performance; return_sale_item = _cloud.return_sale_item
        v2_ready = _cloud.v2_ready; update_product_details = _cloud.update_product_details; find_product_by_barcode = _cloud.find_product_by_barcode
        add_credit_payment = _cloud.add_credit_payment; credit_payments = _cloud.credit_payments
        cash_summary = _cloud.cash_summary; close_cash = _cloud.close_cash; cash_closings = _cloud.cash_closings
        log_action = _cloud.log_action; audit_logs = _cloud.audit_logs; set_user_active = _cloud.set_user_active
        def reset_user_password(user_id, password): _cloud.reset_user_password(user_id, password_hash(password))
        all_users = _cloud.all_users; inventory_snapshot = _cloud.inventory_snapshot
        save_inventory_count = _cloud.save_inventory_count; inventory_history = _cloud.inventory_history
        stores = _cloud.stores; add_store = _cloud.add_store; store_inventory = _cloud.store_inventory
        transfer_stock = _cloud.transfer_stock; transfer_history = _cloud.transfer_history
        get_settings = _cloud.get_settings; update_settings = _cloud.update_settings; dashboard = _cloud.dashboard
except Exception:
    pass
