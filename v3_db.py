"""Couche métier des modules Boutique Senegal V3 (SQLite et Supabase)."""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import pandas as pd

import cloud_db as cloud
import db


def _frame(rows, columns=None): return pd.DataFrame(rows, columns=columns)
def _cloud() -> bool: return cloud.enabled()
def _rows(response): return response.data or []
def _one(table, **filters):
    request=cloud._table(table).select("*")
    for key,value in filters.items(): request=request.eq(key,value)
    rows=_rows(request.limit(1).execute()); return rows[0] if rows else None


def v3_ready() -> bool:
    if not _cloud(): return True
    try:
        cloud._table("documents").select("id").limit(1).execute()
        cloud._table("sale_items").select("id,unit_cost").limit(1).execute()
        cloud._table("users").select("id,can_view_stock,can_discount,can_returns,can_credit").limit(1).execute()
        return True
    except Exception: return False


def v3_error() -> str:
    if not _cloud(): return ""
    try: v3_ready(); cloud._table("documents").select("id").limit(1).execute(); return ""
    except Exception as error: return str(error)[:500]


def create_document(document_type, client_id, valid_until, notes, items, user_id):
    if not items: raise ValueError("Ajoutez au moins un produit.")
    total=sum(int(item["quantity"])*float(item["unit_price"]) for item in items)
    payload={"document_type":document_type,"client_id":client_id,"valid_until":valid_until.isoformat() if valid_until else None,"notes":notes.strip(),"total":total,"created_by":user_id}
    if _cloud():
        document=_rows(cloud._table("documents").insert(payload).execute())[0]
        for item in items: cloud._table("document_items").insert({"document_id":document["id"],"product_id":item["product_id"],"quantity":int(item["quantity"]),"unit_price":float(item["unit_price"])}).execute()
        return int(document["id"])
    with db.connection() as conn:
        cur=conn.execute("INSERT INTO documents(document_type,client_id,valid_until,notes,total,created_by) VALUES(?,?,?,?,?,?)",(document_type,client_id,payload["valid_until"],payload["notes"],total,user_id)); document_id=cur.lastrowid
        for item in items: conn.execute("INSERT INTO document_items(document_id,product_id,quantity,unit_price) VALUES(?,?,?,?)",(document_id,item["product_id"],int(item["quantity"]),float(item["unit_price"])))
        conn.commit(); return int(document_id)


def documents():
    columns=["id","Date","Type","Client","Total","Statut","Validite"]
    if _cloud():
        clients={r["id"]:r["name"] for r in _rows(cloud._table("clients").select("id,name").execute())}
        rows=_rows(cloud._table("documents").select("*").order("created_at",desc=True).limit(300).execute())
        return _frame([{"id":r["id"],"Date":r["created_at"],"Type":r["document_type"],"Client":clients.get(r.get("client_id"),"Comptant"),"Total":r["total"],"Statut":r["status"],"Validite":r.get("valid_until") or ""} for r in rows],columns)
    return db.query("SELECT d.id,d.created_at AS Date,d.document_type AS Type,COALESCE(c.name,'Comptant') AS Client,d.total AS Total,d.status AS Statut,COALESCE(d.valid_until,'') AS Validite FROM documents d LEFT JOIN clients c ON c.id=d.client_id ORDER BY d.created_at DESC LIMIT 300")


def document_details(document_id):
    if _cloud():
        doc=_one("documents",id=document_id)
        if doc is None: raise ValueError("Document introuvable.")
        client=_one("clients",id=doc.get("client_id")) if doc.get("client_id") else None; doc["Client"]=(client or {}).get("name","Comptant")
        products={r["id"]:r["name"] for r in _rows(cloud._table("products").select("id,name").execute())}
        items=_rows(cloud._table("document_items").select("*").eq("document_id",document_id).execute())
        return doc,_frame([{"product_id":r["product_id"],"Produit":products.get(r["product_id"],"Produit"),"Quantite":r["quantity"],"Prix":r["unit_price"],"Total":float(r["quantity"])*float(r["unit_price"])} for r in items])
    doc=db.query("SELECT d.*,COALESCE(c.name,'Comptant') AS Client FROM documents d LEFT JOIN clients c ON c.id=d.client_id WHERE d.id=?",(document_id,))
    if doc.empty: raise ValueError("Document introuvable.")
    items=db.query("SELECT di.product_id,p.name AS Produit,di.quantity AS Quantite,di.unit_price AS Prix,di.quantity*di.unit_price AS Total FROM document_items di LEFT JOIN products p ON p.id=di.product_id WHERE di.document_id=?",(document_id,))
    return doc.iloc[0].to_dict(),items


def document_cart(document_id):
    _,items=document_details(document_id)
    return [{"id":int(r.product_id),"name":str(r.Produit),"quantity":int(r.Quantite),"sale_price":float(r.Prix)} for _,r in items.iterrows()]


def set_document_status(document_id,status):
    if _cloud(): cloud._table("documents").update({"status":status}).eq("id",document_id).execute()
    else: db.execute("UPDATE documents SET status=? WHERE id=?",(status,document_id))


def create_purchase_order(supplier_id, expected_date, notes, items, user_id):
    if not items: raise ValueError("Ajoutez au moins un produit.")
    total=sum(int(i["quantity"])*float(i["unit_cost"]) for i in items); payload={"supplier_id":supplier_id,"expected_date":expected_date.isoformat() if expected_date else None,"notes":notes.strip(),"total":total,"created_by":user_id}
    if _cloud():
        order=_rows(cloud._table("purchase_orders").insert(payload).execute())[0]
        for i in items: cloud._table("purchase_order_items").insert({"purchase_order_id":order["id"],"product_id":i["product_id"],"quantity":int(i["quantity"]),"unit_cost":float(i["unit_cost"])}).execute()
        return int(order["id"])
    with db.connection() as conn:
        cur=conn.execute("INSERT INTO purchase_orders(supplier_id,expected_date,notes,total,created_by) VALUES(?,?,?,?,?)",(supplier_id,payload["expected_date"],payload["notes"],total,user_id)); oid=cur.lastrowid
        for i in items: conn.execute("INSERT INTO purchase_order_items(purchase_order_id,product_id,quantity,unit_cost) VALUES(?,?,?,?)",(oid,i["product_id"],int(i["quantity"]),float(i["unit_cost"])))
        conn.commit(); return int(oid)


def purchase_orders():
    if _cloud():
        suppliers={r["id"]:r["name"] for r in _rows(cloud._table("suppliers").select("id,name").execute())}; rows=_rows(cloud._table("purchase_orders").select("*").order("created_at",desc=True).limit(300).execute())
        return _frame([{"id":r["id"],"Date":r["created_at"],"Fournisseur":suppliers.get(r["supplier_id"],""),"Total":r["total"],"Paye":r["paid"],"Reste":max(0,float(r["total"])-float(r["paid"])),"Statut":r["status"],"Livraison":r.get("expected_date") or ""} for r in rows])
    return db.query("SELECT po.id,po.created_at AS Date,s.name AS Fournisseur,po.total AS Total,po.paid AS Paye,MAX(po.total-po.paid,0) AS Reste,po.status AS Statut,COALESCE(po.expected_date,'') AS Livraison FROM purchase_orders po LEFT JOIN suppliers s ON s.id=po.supplier_id ORDER BY po.created_at DESC LIMIT 300")


def purchase_order_details(order_id):
    if _cloud():
        products={r["id"]:r["name"] for r in _rows(cloud._table("products").select("id,name").execute())}; rows=_rows(cloud._table("purchase_order_items").select("*").eq("purchase_order_id",order_id).execute())
        return _frame([{"id":r["id"],"product_id":r["product_id"],"Produit":products.get(r["product_id"],""),"Commande":r["quantity"],"Recue":r["received_quantity"],"Restante":int(r["quantity"])-int(r["received_quantity"]),"Cout":r["unit_cost"]} for r in rows])
    return db.query("SELECT poi.id,poi.product_id,p.name AS Produit,poi.quantity AS Commande,poi.received_quantity AS Recue,poi.quantity-poi.received_quantity AS Restante,poi.unit_cost AS Cout FROM purchase_order_items poi LEFT JOIN products p ON p.id=poi.product_id WHERE poi.purchase_order_id=?",(order_id,))


def receive_purchase_order_item(order_id,item_id,quantity):
    details=purchase_order_details(order_id); match=details[details.id==item_id]
    if match.empty or quantity<=0 or quantity>int(match.iloc[0].Restante): raise ValueError("Quantité reçue invalide.")
    row=match.iloc[0]; db.adjust_stock(int(row.product_id),int(quantity))
    if _cloud():
        cloud._table("purchase_order_items").update({"received_quantity":int(row.Recue)+int(quantity)}).eq("id",item_id).execute()
    else: db.execute("UPDATE purchase_order_items SET received_quantity=received_quantity+? WHERE id=?",(quantity,item_id))
    remaining=int(purchase_order_details(order_id).Restante.sum())
    status="REÇUE" if remaining==0 else "PARTIELLE"
    if _cloud(): cloud._table("purchase_orders").update({"status":status}).eq("id",order_id).execute()
    else: db.execute("UPDATE purchase_orders SET status=? WHERE id=?",(status,order_id))


def add_supplier_payment(order_id,amount,method,user_id):
    orders=purchase_orders(); match=orders[orders.id==order_id]
    if match.empty or amount<=0 or amount>float(match.iloc[0].Reste): raise ValueError("Paiement fournisseur invalide.")
    if _cloud():
        current=_one("purchase_orders",id=order_id); cloud._table("purchase_orders").update({"paid":float(current["paid"])+float(amount)}).eq("id",order_id).execute(); cloud._table("supplier_payments").insert({"purchase_order_id":order_id,"amount":amount,"payment_method":method,"recorded_by":user_id}).execute()
    else:
        with db.connection() as conn: conn.execute("UPDATE purchase_orders SET paid=paid+? WHERE id=?",(amount,order_id)); conn.execute("INSERT INTO supplier_payments(purchase_order_id,amount,payment_method,recorded_by) VALUES(?,?,?,?)",(order_id,amount,method,user_id)); conn.commit()
    db.add_expense(f"Règlement fournisseur - commande #{order_id}",amount)


def process_return(sale_id,product_id,quantity,reason,resolution,refund_method,user_id):
    details=db.sale_details(sale_id)
    if details is None: raise ValueError("Vente introuvable.")
    sale,items=details; match=items[items.product_id==product_id]
    if match.empty or quantity<=0 or quantity>int(match.iloc[0].Quantite): raise ValueError("Quantité retournée invalide.")
    gross=float(items.Total.sum()) if not items.empty else 0.0; ratio=(float(sale.get("total") or 0)/gross) if gross>0 else 1.0
    amount=float(match.iloc[0].Prix)*int(quantity)*ratio; client_id=sale.get("client_id")
    db.return_sale_item(sale_id,product_id,quantity)
    refund=amount if resolution in {"REMBOURSEMENT","AVOIR"} else 0
    payload={"sale_id":sale_id,"product_id":product_id,"quantity":quantity,"reason":reason.strip(),"resolution":resolution,"refund_method":refund_method if resolution=="REMBOURSEMENT" else "","refund_amount":refund,"processed_by":user_id}
    if _cloud():
        cloud._table("returns").insert(payload).execute()
        if resolution=="AVOIR" and client_id:
            client=_one("clients",id=client_id); cloud._table("clients").update({"store_credit":float(client.get("store_credit") or 0)+refund}).eq("id",client_id).execute()
    else:
        with db.connection() as conn:
            conn.execute("INSERT INTO returns(sale_id,product_id,quantity,reason,resolution,refund_method,refund_amount,processed_by) VALUES(?,?,?,?,?,?,?,?)",(sale_id,product_id,quantity,payload["reason"],resolution,payload["refund_method"],refund,user_id))
            if resolution=="AVOIR" and client_id: conn.execute("UPDATE clients SET store_credit=store_credit+? WHERE id=?",(refund,client_id))
            conn.commit()
    if resolution=="REMBOURSEMENT": add_cash_movement(date.today(),"SORTIE",refund,f"Remboursement ticket #{sale_id}",user_id)
    return refund


def returns_history():
    if _cloud():
        products={r["id"]:r["name"] for r in _rows(cloud._table("products").select("id,name").execute())}; rows=_rows(cloud._table("returns").select("*").order("created_at",desc=True).limit(300).execute())
        return _frame([{"Date":r["created_at"],"Ticket":r["sale_id"],"Produit":products.get(r["product_id"],""),"Quantite":r["quantity"],"Motif":r["reason"],"Solution":r["resolution"],"Montant":r["refund_amount"]} for r in rows])
    return db.query("SELECT r.created_at AS Date,r.sale_id AS Ticket,p.name AS Produit,r.quantity AS Quantite,r.reason AS Motif,r.resolution AS Solution,r.refund_amount AS Montant FROM returns r LEFT JOIN products p ON p.id=r.product_id ORDER BY r.created_at DESC LIMIT 300")


def add_cash_movement(day,movement_type,amount,label,user_id):
    if amount<=0 or movement_type not in {"ENTREE","SORTIE","FOND_INITIAL"}: raise ValueError("Mouvement invalide.")
    payload={"movement_date":day.isoformat(),"movement_type":movement_type,"amount":amount,"label":label.strip(),"recorded_by":user_id}
    if _cloud(): cloud._table("cash_movements").insert(payload).execute()
    else: db.execute("INSERT INTO cash_movements(movement_date,movement_type,amount,label,recorded_by) VALUES(?,?,?,?,?)",(payload["movement_date"],movement_type,amount,payload["label"],user_id))


def cash_movements(day=None):
    if _cloud():
        request=cloud._table("cash_movements").select("*").order("created_at",desc=True)
        if day: request=request.eq("movement_date",day.isoformat())
        rows=_rows(request.limit(300).execute()); return _frame([{"Date":r["movement_date"],"Type":r["movement_type"],"Libelle":r["label"],"Montant":r["amount"]} for r in rows])
    if day: return db.query("SELECT movement_date AS Date,movement_type AS Type,label AS Libelle,amount AS Montant FROM cash_movements WHERE movement_date=? ORDER BY created_at DESC",(day.isoformat(),))
    return db.query("SELECT movement_date AS Date,movement_type AS Type,label AS Libelle,amount AS Montant FROM cash_movements ORDER BY created_at DESC LIMIT 300")


def cash_adjustment(day):
    movements=cash_movements(day)
    if movements.empty: return 0.0
    return sum(float(r.Montant) if r.Type in {"ENTREE","FOND_INITIAL"} else -float(r.Montant) for _,r in movements.iterrows())


def loyalty_customers():
    if _cloud():
        rows=_rows(cloud._table("clients").select("id,name,phone,loyalty_points,store_credit").order("name").execute()); return _frame([{"id":r["id"],"Client":r["name"],"Telephone":r.get("phone",""),"Points":r.get("loyalty_points",0),"Avoir":r.get("store_credit",0)} for r in rows])
    return db.query("SELECT id,name AS Client,phone AS Telephone,loyalty_points AS Points,store_credit AS Avoir FROM clients ORDER BY name")


def adjust_loyalty(client_id,points,credit=0):
    if _cloud():
        row=_one("clients",id=client_id); new_points=max(0,int(row.get("loyalty_points") or 0)+int(points)); new_credit=max(0,float(row.get("store_credit") or 0)+float(credit)); cloud._table("clients").update({"loyalty_points":new_points,"store_credit":new_credit}).eq("id",client_id).execute()
    else: db.execute("UPDATE clients SET loyalty_points=MAX(0,loyalty_points+?),store_credit=MAX(0,store_credit+?) WHERE id=?",(int(points),float(credit),client_id))


def permissions():
    columns=["id","Nom","Identifiant","Stock","Remises","Retours","Credits"]
    if _cloud(): rows=_rows(cloud._table("users").select("id,display_name,username,role,can_view_stock,can_discount,can_returns,can_credit").eq("role","seller").execute()); return _frame([{"id":r["id"],"Nom":r["display_name"],"Identifiant":r["username"],"Stock":r["can_view_stock"],"Remises":r["can_discount"],"Retours":r["can_returns"],"Credits":r["can_credit"]} for r in rows],columns)
    return db.query("SELECT id,display_name AS Nom,username AS Identifiant,can_view_stock AS Stock,can_discount AS Remises,can_returns AS Retours,can_credit AS Credits FROM users WHERE role='seller'")


def update_permissions(user_id,view_stock,discount,returns,credit):
    payload={"can_view_stock":bool(view_stock),"can_discount":bool(discount),"can_returns":bool(returns),"can_credit":bool(credit)}
    if _cloud(): cloud._table("users").update(payload).eq("id",user_id).eq("role","seller").execute()
    else: db.execute("UPDATE users SET can_view_stock=?,can_discount=?,can_returns=?,can_credit=? WHERE id=? AND role='seller'",(int(view_stock),int(discount),int(returns),int(credit),user_id))


def user_permissions(user):
    if user.get("role")=="admin": return {"stock":True,"discount":True,"returns":True,"credit":True}
    row=None
    try:
        if _cloud(): row=_one("users",id=int(user["id"]))
        else:
            result=db.query("SELECT can_view_stock,can_discount,can_returns,can_credit FROM users WHERE id=?",(int(user["id"]),)); row=None if result.empty else result.iloc[0].to_dict()
    except Exception: row={}
    row=row or {}; return {"stock":bool(row.get("can_view_stock",False)),"discount":bool(row.get("can_discount",False)),"returns":bool(row.get("can_returns",False)),"credit":bool(row.get("can_credit",False))}


def add_lot(product_id,batch_number,expiry_date,quantity,notes=""):
    if not batch_number.strip() or quantity<0: raise ValueError("Lot invalide.")
    payload={"product_id":product_id,"batch_number":batch_number.strip(),"expiry_date":expiry_date.isoformat(),"quantity":quantity,"notes":notes.strip()}
    if _cloud(): cloud._table("product_lots").insert(payload).execute()
    else: db.execute("INSERT INTO product_lots(product_id,batch_number,expiry_date,quantity,notes) VALUES(?,?,?,?,?)",(product_id,payload["batch_number"],payload["expiry_date"],quantity,payload["notes"]))


def lots():
    if _cloud():
        products={r["id"]:r["name"] for r in _rows(cloud._table("products").select("id,name").execute())}; rows=_rows(cloud._table("product_lots").select("*").order("expiry_date").execute())
        return _frame([{"id":r["id"],"Produit":products.get(r["product_id"],""),"Lot":r["batch_number"],"Expiration":r["expiry_date"],"Quantite":r["quantity"],"Notes":r.get("notes","")} for r in rows])
    return db.query("SELECT l.id,p.name AS Produit,l.batch_number AS Lot,l.expiry_date AS Expiration,l.quantity AS Quantite,l.notes AS Notes FROM product_lots l LEFT JOIN products p ON p.id=l.product_id ORDER BY l.expiry_date")


def expiry_alerts(days=30):
    frame=lots(); columns=["Statut","Produit","Lot","Expiration","Quantite"]
    if frame.empty: return pd.DataFrame(columns=columns)
    frame["Jours"] = pd.to_datetime(frame.Expiration).dt.date.map(lambda d:(d-date.today()).days); frame=frame[frame.Jours<=days].copy()
    frame["Statut"]=frame.Jours.map(lambda d:"EXPIRÉ" if d<0 else ("URGENT" if d<=7 else "À SURVEILLER")); return frame[["Statut","Produit","Lot","Expiration","Quantite"]]


def sync_offline_sales(bundle,seller_id,user_id):
    if bundle.get("format")!="boutique-offline-sales" or int(bundle.get("version",0))!=1: raise ValueError("Fichier hors connexion invalide.")
    done=0; skipped=0; errors=[]
    for sale in bundle.get("sales",[]):
        offline_id=str(sale.get("offline_id","")).strip()
        if not offline_id: errors.append("Identifiant manquant"); continue
        exists=_one("offline_imports",offline_id=offline_id) if _cloud() else (not db.query("SELECT offline_id FROM offline_imports WHERE offline_id=?",(offline_id,)).empty)
        if exists: skipped+=1; continue
        try:
            items=sale.get("items",[]); db.save_sale(items,seller_id,None,sum(int(i["quantity"])*float(i["sale_price"]) for i in items),"Especes",0)
            payload={"offline_id":offline_id,"imported_by":user_id,"original_created_at":sale.get("created_at")}
            if _cloud(): cloud._table("offline_imports").insert(payload).execute()
            else: db.execute("INSERT INTO offline_imports(offline_id,imported_by,original_created_at) VALUES(?,?,?)",(offline_id,user_id,payload["original_created_at"]))
            done+=1
        except Exception as error: errors.append(f"{offline_id}: {error}")
    return {"imported":done,"skipped":skipped,"errors":errors}
