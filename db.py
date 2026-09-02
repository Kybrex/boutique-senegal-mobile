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
        """)
        _column(conn, "products", "supplier_id", "INTEGER")
        _column(conn, "sales", "client_id", "INTEGER")
        _column(conn, "sales", "discount", "REAL NOT NULL DEFAULT 0")
        _column(conn, "sellers", "email", "TEXT")
        _column(conn, "suppliers", "email", "TEXT")
        _column(conn, "clients", "email", "TEXT")
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
def set_stock(product_id: int, stock: int) -> None: execute("UPDATE products SET stock=? WHERE id=?", (stock, product_id))
def adjust_stock(product_id: int, adjustment: int) -> None:
    with connection() as conn:
        current = conn.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()
        if current is None: raise ValueError("Produit introuvable")
        new_stock = current["stock"] + adjustment
        if new_stock < 0: raise ValueError("Le stock ne peut pas etre negatif")
        conn.execute("UPDATE products SET stock=? WHERE id=?", (new_stock, product_id)); conn.commit()
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
        conn.commit()
    return sale_id, gross, total
def sale_details(sale_id: int) -> tuple[dict, pd.DataFrame] | None:
    sale = query("SELECT s.id,s.created_at,s.client_id,s.total,s.discount,s.paid,s.payment_method,COALESCE(c.name,'Comptant') AS client FROM sales s LEFT JOIN clients c ON c.id=s.client_id WHERE s.id=?", (sale_id,))
    if sale.empty:
        return None
    items = query("SELECT p.name AS Produit,si.quantity AS Quantite,si.unit_price AS Prix,si.quantity*si.unit_price AS Total FROM sale_items si LEFT JOIN products p ON p.id=si.product_id WHERE si.sale_id=? ORDER BY si.id", (sale_id,))
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
        conn.execute("DELETE FROM sale_items WHERE sale_id=?", (sale_id,))
        conn.execute("DELETE FROM sales WHERE id=?", (sale_id,))
        conn.commit()
def add_expense(label: str, amount: float) -> None: execute("INSERT INTO expenses(label,amount) VALUES(?,?)", (label.strip(), amount))
def products() -> pd.DataFrame: return query("SELECT p.id,p.name AS Produit,p.category AS Categorie,p.purchase_price AS Achat,p.sale_price AS Vente,p.stock AS Stock,p.min_stock AS Minimum,COALESCE(s.name,'') AS Fournisseur FROM products p LEFT JOIN suppliers s ON s.id=p.supplier_id ORDER BY p.name")
def sellers() -> pd.DataFrame: return query("SELECT id,name AS Vendeur,phone AS Telephone,email AS Email FROM sellers WHERE active=1 ORDER BY name")
def suppliers() -> pd.DataFrame: return query("SELECT id,name AS Fournisseur,contact AS Contact,phone AS Telephone,email AS Email,address AS Adresse FROM suppliers ORDER BY name")
def clients() -> pd.DataFrame: return query("SELECT id,name AS Client,phone AS Telephone,email AS Email,address AS Adresse FROM clients ORDER BY name")
def users() -> pd.DataFrame: return query("SELECT u.id,u.username AS Identifiant,u.display_name AS Nom,u.role AS Role,COALESCE(s.name,'') AS Vendeur FROM users u LEFT JOIN sellers s ON s.id=u.seller_id WHERE u.active=1 ORDER BY u.role,u.display_name")
def low_stock() -> pd.DataFrame: return query("SELECT name AS Produit,stock AS Stock,min_stock AS Minimum FROM products WHERE stock<=min_stock ORDER BY stock")
def today_summary() -> pd.DataFrame: return query("SELECT COALESCE(SUM(total),0) AS sales, COUNT(*) AS transactions FROM sales WHERE date(created_at)=?", (date.today().isoformat(),))
def report(start: date, end: date) -> pd.DataFrame: return query("SELECT s.id AS Ticket,s.created_at AS Date,COALESCE(v.name,'Inconnu') AS Vendeur,COALESCE(c.name,'Comptant') AS Client,s.total AS Total,s.discount AS Reduction,s.paid AS Encaisse,s.payment_method AS Paiement FROM sales s LEFT JOIN sellers v ON v.id=s.seller_id LEFT JOIN clients c ON c.id=s.client_id WHERE date(s.created_at) BETWEEN ? AND ? ORDER BY s.created_at DESC", (start.isoformat(), end.isoformat()))
def expenses(start: date, end: date) -> pd.DataFrame: return query("SELECT created_at AS Date,label AS Libelle,amount AS Montant FROM expenses WHERE date(created_at) BETWEEN ? AND ? ORDER BY created_at DESC", (start.isoformat(), end.isoformat()))

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
except Exception:
    pass
