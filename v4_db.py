"""Couche métier Boutique Senegal V4, compatible SQLite et Supabase."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import unicodedata

import pandas as pd

import cloud_db as cloud
import db
import v3_db as v3


def _cloud() -> bool: return cloud.enabled()
def _rows(response): return response.data or []
def _frame(rows, columns=None): return pd.DataFrame(rows, columns=columns)
def _one(table, **filters):
    request=cloud._table(table).select("*")
    for key,value in filters.items(): request=request.eq(key,value)
    rows=_rows(request.limit(1).execute()); return rows[0] if rows else None


def v4_ready() -> bool:
    if not _cloud(): return True
    try:
        cloud._table("product_variants").select("id").limit(1).execute()
        cloud._table("notification_events").select("id").limit(1).execute()
        cloud._table("sellers").select("id,commission_rate").limit(1).execute()
        cloud._table("sales").select("id,commission_amount,store_id").limit(1).execute()
        return True
    except Exception: return False


def v4_error() -> str:
    if not _cloud(): return ""
    try: v4_ready(); cloud._table("product_variants").select("id").limit(1).execute(); return ""
    except Exception as error: return str(error)[:500]


def variants(product_id: int | None = None) -> pd.DataFrame:
    columns=["id","product_id","Produit","Variante","SKU","Code_barres","Stock","Ajustement_prix","Actif"]
    if _cloud():
        products={r["id"]:r["name"] for r in _rows(cloud._table("products").select("id,name").execute())}
        request=cloud._table("product_variants").select("*").order("name")
        if product_id is not None: request=request.eq("product_id",product_id)
        rows=_rows(request.execute())
        return _frame([{"id":r["id"],"product_id":r["product_id"],"Produit":products.get(r["product_id"],""),"Variante":r["name"],"SKU":r.get("sku","") or "","Code_barres":r.get("barcode","") or "","Stock":r["stock"],"Ajustement_prix":r["price_adjustment"],"Actif":r["active"]} for r in rows],columns)
    where=" WHERE pv.product_id=?" if product_id is not None else ""; params=(product_id,) if product_id is not None else ()
    return db.query("SELECT pv.id,pv.product_id,p.name AS Produit,pv.name AS Variante,pv.sku AS SKU,COALESCE(pv.barcode,'') AS Code_barres,pv.stock AS Stock,pv.price_adjustment AS Ajustement_prix,pv.active AS Actif FROM product_variants pv JOIN products p ON p.id=pv.product_id"+where+" ORDER BY p.name,pv.name",params)


def add_variant(product_id: int, name: str, sku: str, barcode: str, stock: int, price_adjustment: float) -> None:
    if not name.strip() or stock<0: raise ValueError("Nom de variante ou stock invalide.")
    payload={"product_id":product_id,"name":name.strip(),"sku":sku.strip(),"barcode":barcode.strip() or None,"stock":int(stock),"price_adjustment":float(price_adjustment)}
    if _cloud(): cloud._table("product_variants").insert(payload).execute()
    else: db.execute("INSERT INTO product_variants(product_id,name,sku,barcode,stock,price_adjustment) VALUES(?,?,?,?,?,?)",(product_id,payload["name"],payload["sku"],payload["barcode"],stock,price_adjustment))


def update_variant_stock(variant_id: int, stock: int) -> None:
    if stock<0: raise ValueError("Le stock ne peut pas être négatif.")
    if _cloud(): cloud._table("product_variants").update({"stock":int(stock)}).eq("id",variant_id).execute()
    else: db.execute("UPDATE product_variants SET stock=? WHERE id=?",(stock,variant_id))


def set_commission_rate(seller_id: int, rate: float) -> None:
    if rate<0 or rate>100: raise ValueError("Le taux doit être compris entre 0 et 100 %.")
    if _cloud(): cloud._table("sellers").update({"commission_rate":float(rate)}).eq("id",seller_id).execute()
    else: db.execute("UPDATE sellers SET commission_rate=? WHERE id=?",(rate,seller_id))


def commission_rates() -> pd.DataFrame:
    if _cloud():
        rows=_rows(cloud._table("sellers").select("id,name,commission_rate").eq("active",True).order("name").execute())
        return _frame([{"id":r["id"],"Vendeur":r["name"],"Taux":r.get("commission_rate",0)} for r in rows],["id","Vendeur","Taux"])
    return db.query("SELECT id,name AS Vendeur,commission_rate AS Taux FROM sellers WHERE active=1 ORDER BY name")


def seller_store_assignments() -> pd.DataFrame:
    columns=["id","Vendeur","Identifiant","store_id","Boutique"]
    if _cloud():
        stores={r["id"]:r["name"] for r in _rows(cloud._table("stores").select("id,name").execute())}; rows=_rows(cloud._table("users").select("id,display_name,username,store_id").eq("role","seller").eq("active",True).execute())
        return _frame([{"id":r["id"],"Vendeur":r["display_name"],"Identifiant":r["username"],"store_id":r.get("store_id") or 1,"Boutique":stores.get(r.get("store_id") or 1,"Boutique principale")} for r in rows],columns)
    return db.query("SELECT u.id,u.display_name AS Vendeur,u.username AS Identifiant,COALESCE(u.store_id,1) AS store_id,COALESCE(s.name,'Boutique principale') AS Boutique FROM users u LEFT JOIN stores s ON s.id=COALESCE(u.store_id,1) WHERE u.role='seller' AND u.active=1 ORDER BY u.display_name")


def set_user_store(user_id: int, store_id: int) -> None:
    if _cloud(): cloud._table("users").update({"store_id":store_id}).eq("id",user_id).eq("role","seller").execute()
    else: db.execute("UPDATE users SET store_id=? WHERE id=? AND role='seller'",(store_id,user_id))


def store_for_seller(seller_id: int) -> int:
    if _cloud():
        row=_one("users",seller_id=seller_id,role="seller"); return int((row or {}).get("store_id") or 1)
    rows=db.query("SELECT COALESCE(store_id,1) AS store_id FROM users WHERE seller_id=? AND role='seller' LIMIT 1",(seller_id,)); return 1 if rows.empty else int(rows.iloc[0].store_id)


def commission_report(start: date, end: date) -> pd.DataFrame:
    if _cloud():
        sellers={r["id"]:r["name"] for r in _rows(cloud._table("sellers").select("id,name").execute())}; rows=_rows(cloud._table("sales").select("seller_id,total,commission_amount").gte("created_at",start.isoformat()).lt("created_at",(end+timedelta(days=1)).isoformat()).execute())
        totals={}
        for r in rows:
            item=totals.setdefault(r.get("seller_id"),{"Ventes":0.0,"Commission":0.0,"Tickets":0}); item["Ventes"]+=float(r.get("total") or 0); item["Commission"]+=float(r.get("commission_amount") or 0); item["Tickets"]+=1
        return _frame([{"Vendeur":sellers.get(k,"Inconnu"),**v} for k,v in totals.items()],["Vendeur","Tickets","Ventes","Commission"])
    return db.query("SELECT s.name AS Vendeur,COUNT(v.id) AS Tickets,COALESCE(SUM(v.total),0) AS Ventes,COALESCE(SUM(v.commission_amount),0) AS Commission FROM sellers s LEFT JOIN sales v ON v.seller_id=s.id AND date(v.created_at) BETWEEN ? AND ? WHERE s.active=1 GROUP BY s.id,s.name ORDER BY Ventes DESC",(start.isoformat(),end.isoformat()))


def set_admin_pin(pin: str, approval_percent: float, backup_days: int) -> None:
    if len(pin)!=4 or not pin.isdigit(): raise ValueError("Le PIN doit contenir exactement 4 chiffres.")
    payload={"admin_pin_hash":db.password_hash(pin),"discount_approval_percent":float(approval_percent),"auto_backup_days":int(backup_days)}
    if _cloud(): cloud._table("shop_settings").update(payload).eq("id",1).execute()
    else: db.execute("UPDATE shop_settings SET admin_pin_hash=?,discount_approval_percent=?,auto_backup_days=? WHERE id=1",tuple(payload.values()))


def approval_settings() -> dict:
    settings=db.get_settings(); return {"configured":bool(settings.get("admin_pin_hash")),"threshold":float(settings.get("discount_approval_percent",10) or 10),"backup_days":int(settings.get("auto_backup_days",7) or 7)}


def verify_admin_pin(pin: str, user_id: int | None = None, action: str = "APPROBATION", amount: float = 0, details: str = "") -> bool:
    settings=db.get_settings(); valid=db.valid_password(pin,str(settings.get("admin_pin_hash","") or ""))
    if valid:
        payload={"user_id":user_id,"action":action,"amount":float(amount),"details":details[:500]}
        if _cloud(): cloud._table("approval_logs").insert(payload).execute()
        else: db.execute("INSERT INTO approval_logs(user_id,action,amount,details) VALUES(?,?,?,?)",(user_id,action,amount,details[:500]))
    return valid


def atomic_save_sale(cart, seller_id, client_id, paid, method, discount, due_date=None, store_id=1):
    """Enregistre la vente et le stock dans une seule transaction."""
    if not cart: raise ValueError("Le ticket est vide.")
    if _cloud():
        params={"p_seller_id":seller_id,"p_client_id":client_id,"p_paid":float(paid),"p_method":method,"p_discount":float(discount),"p_due_date":due_date.isoformat() if hasattr(due_date,"isoformat") else due_date,"p_store_id":int(store_id),"p_items":[{"product_id":int(i["id"]),"variant_id":i.get("variant_id"),"quantity":int(i["quantity"]),"unit_price":float(i["sale_price"])} for i in cart]}
        result=cloud.client().rpc("save_sale_atomic",params).execute().data
        data=result[0] if isinstance(result,list) and result else result
        if not isinstance(data,dict): raise ValueError("Réponse de vente Supabase invalide.")
        return int(data["sale_id"]),float(data["gross"]),float(data["total"])
    with db.connection() as conn:
        product_rows={}; variant_rows={}; gross=0.0
        for item in cart:
            product=conn.execute("SELECT * FROM products WHERE id=?",(item["id"],)).fetchone(); qty=int(item["quantity"])
            if product is None: raise ValueError("Produit introuvable.")
            available=int(product["stock"]) if int(store_id)==1 else int((conn.execute("SELECT stock FROM store_stock WHERE store_id=? AND product_id=?",(store_id,item["id"])).fetchone() or {"stock":0})["stock"])
            if available<qty: raise ValueError("Stock insuffisant dans la boutique de vente.")
            product_rows[int(item["id"])]=product; gross+=qty*float(item["sale_price"])
            if item.get("variant_id") is not None:
                variant=conn.execute("SELECT * FROM product_variants WHERE id=? AND product_id=? AND active=1",(item["variant_id"],item["id"])).fetchone()
                if variant is None or int(variant["stock"])<qty: raise ValueError("Stock insuffisant pour la variante.")
                variant_rows[int(item["variant_id"])]=variant
        discount=max(0,min(float(discount),gross)); total=gross-discount; due_value=due_date.isoformat() if hasattr(due_date,"isoformat") else due_date
        rate_row=conn.execute("SELECT commission_rate FROM sellers WHERE id=?",(seller_id,)).fetchone(); rate=float(rate_row["commission_rate"] or 0) if rate_row else 0
        cursor=conn.execute("INSERT INTO sales(seller_id,client_id,total,discount,paid,payment_method,due_date,store_id,commission_amount) VALUES(?,?,?,?,?,?,?,?,?)",(seller_id,client_id,total,discount,paid,method,due_value,store_id,total*rate/100)); ticket=int(cursor.lastrowid)
        for item in cart:
            qty=int(item["quantity"]); product=product_rows[int(item["id"])]; variant_id=item.get("variant_id")
            conn.execute("INSERT INTO sale_items(sale_id,product_id,variant_id,quantity,unit_price,unit_cost) VALUES(?,?,?,?,?,?)",(ticket,item["id"],variant_id,qty,item["sale_price"],float(product["purchase_price"] or 0)))
            if int(store_id)==1: conn.execute("UPDATE products SET stock=stock-? WHERE id=?",(qty,item["id"]))
            if variant_id is not None: conn.execute("UPDATE product_variants SET stock=stock-? WHERE id=?",(qty,variant_id))
            current=(int(product["stock"]) if int(store_id)==1 else int(conn.execute("SELECT stock FROM store_stock WHERE store_id=? AND product_id=?",(store_id,item["id"])).fetchone()["stock"]))-qty
            conn.execute("INSERT INTO store_stock(store_id,product_id,stock) VALUES(?,?,?) ON CONFLICT(store_id,product_id) DO UPDATE SET stock=excluded.stock",(store_id,item["id"],current))
        if client_id and paid>0: conn.execute("UPDATE clients SET loyalty_points=loyalty_points+? WHERE id=?",(int(float(paid)//1000),client_id))
        conn.commit(); return ticket,gross,total


def _norm(value) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD",str(value or "")) if not unicodedata.combining(c)).strip().lower()


def import_rows(kind: str, rows: list[dict]) -> dict:
    """Importe produits, clients ou fournisseurs par fusion sans doublons."""
    aliases={
        "products":{"name":["nom","produit","name"],"category":["categorie","catégorie","category"],"purchase_price":["prix achat","achat","purchase_price"],"sale_price":["prix vente","vente","sale_price"],"stock":["stock","quantite","quantité"],"min_stock":["minimum","seuil","min_stock"],"barcode":["code-barres","code_barres","barcode"]},
        "clients":{"name":["nom","client","name"],"phone":["telephone","téléphone","phone"],"email":["email","e-mail"],"address":["adresse","address"]},
        "suppliers":{"name":["nom","fournisseur","name"],"contact":["contact"],"phone":["telephone","téléphone","phone"],"email":["email","e-mail"],"address":["adresse","address"]},
    }
    if kind not in aliases: raise ValueError("Type d'import inconnu.")
    def convert(row):
        normalized={_norm(k):v for k,v in row.items()}; out={}
        for target,names in aliases[kind].items():
            for name in names:
                if _norm(name) in normalized and pd.notna(normalized[_norm(name)]): out[target]=normalized[_norm(name)]; break
        return out
    prepared=[convert(r) for r in rows]; prepared=[r for r in prepared if str(r.get("name","")).strip()]
    inserted=updated=ignored=0
    for row in prepared:
        name=str(row["name"]).strip()
        if kind=="products":
            row.update({"name":name,"category":str(row.get("category","") or ""),"purchase_price":float(row.get("purchase_price",0) or 0),"sale_price":float(row.get("sale_price",0) or 0),"stock":int(float(row.get("stock",0) or 0)),"min_stock":int(float(row.get("min_stock",0) or 0)),"barcode":str(row.get("barcode","") or "").strip() or None})
            if row["sale_price"]<=0: ignored+=1; continue
        else: row.update({"name":name,"phone":str(row.get("phone","") or ""),"email":str(row.get("email","") or ""),"address":str(row.get("address","") or "")})
        if _cloud():
            existing=_one(kind,name=name)
            if existing: cloud._table(kind).update({k:v for k,v in row.items() if k!="name"}).eq("id",existing["id"]).execute(); identifier=int(existing["id"]); updated+=1
            else: identifier=int(_rows(cloud._table(kind).insert(row).execute())[0]["id"]); inserted+=1
        else:
            existing=db.query(f"SELECT id FROM {kind} WHERE name=?",(name,))
            if existing.empty:
                columns=list(row)
                with db.connection() as conn: cursor=conn.execute(f"INSERT INTO {kind}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",tuple(row[c] for c in columns)); identifier=int(cursor.lastrowid); conn.commit()
                inserted+=1
            else:
                identifier=int(existing.iloc[0].id); columns=[c for c in row if c!="name"]; db.execute(f"UPDATE {kind} SET {','.join(c+'=?' for c in columns)} WHERE id=?",tuple(row[c] for c in columns)+(identifier,)); updated+=1
        if kind=="products": db.set_stock(identifier,int(row["stock"]))
    return {"inserted":inserted,"updated":updated,"ignored":ignored}


def global_search(term: str) -> dict[str,pd.DataFrame]:
    needle=_norm(term)
    if len(needle)<2: return {}
    frames={"Produits":db.products(),"Clients":db.clients(),"Fournisseurs":db.suppliers(),"Ventes":db.report(date(2000,1,1),date.today()),"Documents":v3.documents() if v3.v3_ready() else pd.DataFrame()}
    result={}
    for name,frame in frames.items():
        if frame.empty: continue
        mask=frame.astype(str).apply(lambda col: col.map(_norm).str.contains(needle,regex=False)).any(axis=1)
        if mask.any(): result[name]=frame[mask].head(100)
    return result


def reorder_forecast(days: int = 30) -> pd.DataFrame:
    products=db.products(); start=date.today()-timedelta(days=days); performance=db.product_performance(start,date.today())
    sold={str(r.Produit):float(r.Quantite) for _,r in performance.iterrows()} if not performance.empty else {}
    rows=[]
    for _,p in products.iterrows():
        qty=sold.get(str(p.Produit),0); daily=qty/max(1,days); cover=(float(p.Stock)/daily) if daily>0 else None; suggested=max(0,int(round(daily*30+float(p.Minimum)-float(p.Stock))))
        rows.append({"Produit":p.Produit,"Stock":int(p.Stock),"Vendu_30j":int(qty),"Moyenne_jour":round(daily,2),"Jours_couverture":round(cover,1) if cover is not None else "∞","Commande_suggeree":suggested,"Priorite":"URGENT" if cover is not None and cover<=7 else ("À COMMANDER" if suggested>0 else "OK")})
    return _frame(rows).sort_values(["Commande_suggeree","Stock"],ascending=[False,True]) if rows else _frame([])


def client_statement(client_id: int) -> pd.DataFrame: return db.client_history(client_id)


def supplier_statement(supplier_id: int) -> pd.DataFrame:
    if _cloud():
        rows=_rows(cloud._table("purchase_orders").select("id,created_at,total,paid,status,expected_date").eq("supplier_id",supplier_id).order("created_at",desc=True).execute())
        return _frame([{"Commande":r["id"],"Date":r["created_at"],"Total":r["total"],"Paye":r["paid"],"Reste":max(0,float(r["total"])-float(r["paid"])),"Statut":r["status"],"Livraison":r.get("expected_date") or ""} for r in rows])
    return db.query("SELECT id AS Commande,created_at AS Date,total AS Total,paid AS Paye,MAX(total-paid,0) AS Reste,status AS Statut,COALESCE(expected_date,'') AS Livraison FROM purchase_orders WHERE supplier_id=? ORDER BY created_at DESC",(supplier_id,))


def refresh_notifications() -> pd.DataFrame:
    events=[]
    for _,r in db.credit_alerts().iterrows(): events.append((f"credit:{int(r.Ticket)}:{r.Statut}","CREDIT",f"{r.Statut} — {r.Client}",f"Ticket #{int(r.Ticket)}, reste {float(r.Reste):.0f} FCFA, échéance {r.Echeance}","URGENT" if "RETARD" in str(r.Statut) or "24" in str(r.Statut) else "ATTENTION"))
    for _,r in db.low_stock().iterrows(): events.append((f"stock:{r.Produit}","STOCK",f"Stock faible — {r.Produit}",f"Stock {int(r.Stock)}, minimum {int(r.Minimum)}","URGENT" if int(r.Stock)<=0 else "ATTENTION"))
    if v3.v3_ready():
        for _,r in v3.expiry_alerts().iterrows(): events.append((f"lot:{r.Produit}:{r.Lot}","EXPIRATION",f"Lot {r.Statut} — {r.Produit}",f"Lot {r.Lot}, expiration {r.Expiration}","URGENT" if r.Statut in {"EXPIRÉ","URGENT"} else "ATTENTION"))
        orders=v3.purchase_orders()
        for _,r in orders.iterrows():
            if r.Livraison and str(r.Statut)!="REÇUE":
                try:
                    delay=(date.today()-pd.to_datetime(r.Livraison).date()).days
                    if delay>=0: events.append((f"order:{int(r.id)}","COMMANDE",f"Commande fournisseur en retard #{int(r.id)}",f"{r.Fournisseur}, prévue le {r.Livraison}","URGENT"))
                except Exception: pass
    try:
        if _cloud(): cloud._table("notification_events").update({"resolved":True}).eq("resolved",False).execute()
        else: db.execute("UPDATE notification_events SET resolved=1 WHERE resolved=0")
    except Exception: pass
    for key,category,title,details,severity in events:
        payload={"event_key":key,"category":category,"title":title,"details":details,"severity":severity,"resolved":False}
        try:
            if _cloud(): cloud._table("notification_events").upsert(payload,on_conflict="event_key").execute()
            else: db.execute("INSERT INTO notification_events(event_key,category,title,details,severity,resolved) VALUES(?,?,?,?,?,0) ON CONFLICT(event_key) DO UPDATE SET title=excluded.title,details=excluded.details,severity=excluded.severity,resolved=0",(key,category,title,details,severity))
        except Exception: pass
    if _cloud(): rows=_rows(cloud._table("notification_events").select("*").eq("resolved",False).order("created_at",desc=True).limit(300).execute())
    else: rows=json.loads(db.query("SELECT * FROM notification_events WHERE resolved=0 ORDER BY created_at DESC LIMIT 300").to_json(orient="records"))
    return _frame([{"Date":r.get("created_at",""),"Niveau":r.get("severity",""),"Categorie":r.get("category",""),"Alerte":r.get("title",""),"Details":r.get("details","")} for r in rows],["Date","Niveau","Categorie","Alerte","Details"])


def automatic_backup_if_due() -> str:
    """Crée au plus une sauvegarde automatique selon la fréquence configurée."""
    days=approval_settings()["backup_days"]
    try:
        if _cloud(): recent=_rows(cloud._table("backup_runs").select("created_at,status").eq("status","OK").order("created_at",desc=True).limit(1).execute())
        else: recent=json.loads(db.query("SELECT created_at,status FROM backup_runs WHERE status='OK' ORDER BY created_at DESC LIMIT 1").to_json(orient="records"))
        if recent and datetime.fromisoformat(str(recent[0]["created_at"]).replace("Z","+00:00")).date() >= date.today()-timedelta(days=max(1,days)): return "à jour"
        bundle=db.backup_bundle(); payload=json.dumps(bundle,ensure_ascii=False,default=str).encode("utf-8"); path=f"boutique-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.json"
        if _cloud():
            cloud.client().storage.from_("automatic-backups").upload(path,payload,{"content-type":"application/json","upsert":"false"}); cloud._table("backup_runs").insert({"storage_path":path,"row_count":sum(len(v) for v in bundle["tables"].values()),"status":"OK"}).execute()
        else:
            folder=Path(__file__).parent/"backups"; folder.mkdir(exist_ok=True); (folder/path).write_bytes(payload); db.execute("INSERT INTO backup_runs(storage_path,row_count,status) VALUES(?,?,?)",(str(folder/path),sum(len(v) for v in bundle["tables"].values()),"OK"))
        return "créée"
    except Exception as error: return f"indisponible: {str(error)[:140]}"


def backup_history() -> pd.DataFrame:
    if _cloud(): rows=_rows(cloud._table("backup_runs").select("*").order("created_at",desc=True).limit(100).execute())
    else: rows=json.loads(db.query("SELECT * FROM backup_runs ORDER BY created_at DESC LIMIT 100").to_json(orient="records"))
    return _frame([{"Date":r.get("created_at",""),"Fichier":r.get("storage_path",""),"Lignes":r.get("row_count",0),"Statut":r.get("status","")} for r in rows],["Date","Fichier","Lignes","Statut"])


def owner_dashboard(start: date, end: date) -> dict:
    sales=db.report(start,end); stores=db.stores(); store_names={int(r.id):r.Boutique for _,r in stores.iterrows()}
    if _cloud(): raw=_rows(cloud._table("sales").select("store_id,total,paid,commission_amount").gte("created_at",start.isoformat()).lt("created_at",(end+timedelta(days=1)).isoformat()).execute())
    else: raw=json.loads(db.query("SELECT store_id,total,paid,commission_amount FROM sales WHERE date(created_at) BETWEEN ? AND ?",(start.isoformat(),end.isoformat())).to_json(orient="records"))
    totals={}
    for r in raw:
        sid=int(r.get("store_id") or 1); item=totals.setdefault(sid,{"Ventes":0.0,"Encaisse":0.0,"Creances":0.0,"Commissions":0.0,"Tickets":0}); item["Ventes"]+=float(r.get("total") or 0); item["Encaisse"]+=float(r.get("paid") or 0); item["Creances"]+=max(0,float(r.get("total") or 0)-float(r.get("paid") or 0)); item["Commissions"]+=float(r.get("commission_amount") or 0); item["Tickets"]+=1
    product_costs={int(r.id):float(r.Achat or 0) for _,r in db.products().iterrows()}
    for _,store in stores.iterrows():
        sid=int(store.id); inventory=db.store_inventory(sid); item=totals.setdefault(sid,{"Ventes":0.0,"Encaisse":0.0,"Creances":0.0,"Commissions":0.0,"Tickets":0}); item["Unites_stock"]=int(inventory.Stock.sum()) if not inventory.empty else 0; item["Valeur_stock"]=sum(int(r.Stock)*product_costs.get(int(r.id),0) for _,r in inventory.iterrows()) if not inventory.empty else 0
    by_store=_frame([{"Boutique":store_names.get(sid,f"Boutique #{sid}"),**values} for sid,values in totals.items()],["Boutique","Tickets","Ventes","Encaisse","Creances","Commissions","Unites_stock","Valeur_stock"])
    return {"sales":float(sales.Total.sum()) if not sales.empty else 0.0,"tickets":len(sales),"debt":float(db.dashboard(start,end)["debt"]),"stores":by_store,"commissions":commission_report(start,end),"forecast":reorder_forecast()}
