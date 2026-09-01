from __future__ import annotations
from datetime import datetime
from html import escape

def make_receipt(ticket: int, cart: list[dict], seller: str, client: str, gross: float, discount: float, total: float, paid: float, payment: str) -> str:
    lines = "".join(f"<tr><td>{escape(str(item['name']))} x{item['quantity']}</td><td>{item['quantity'] * item['sale_price']:,.0f} FCFA</td></tr>" for item in cart)
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>body{{font-family:Arial;max-width:320px;margin:auto}}h2,p{{text-align:center}}table{{width:100%;border-collapse:collapse}}td{{padding:5px;border-bottom:1px dashed #aaa}}.total{{font-size:18px;font-weight:bold}}</style></head><body><h2>BOUTIQUE SENEGAL</h2><p>Ticket #{ticket}<br>{datetime.now():%d/%m/%Y %H:%M}<br>Vendeur: {escape(seller)}<br>Client: {escape(client)}</p><table>{lines}</table><p>Sous-total: {gross:,.0f} FCFA<br>Reduction: {discount:,.0f} FCFA</p><p class='total'>TOTAL: {total:,.0f} FCFA</p><p>Verse: {paid:,.0f} FCFA<br>Monnaie: {paid-total:,.0f} FCFA<br>Paiement: {escape(payment)}</p><p>Merci pour votre achat !</p></body></html>"""
