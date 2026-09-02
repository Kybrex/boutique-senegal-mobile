from __future__ import annotations
from datetime import datetime
from html import escape
from io import BytesIO

def make_receipt(ticket: int, cart: list[dict], seller: str, client: str, gross: float, discount: float, total: float, paid: float, payment: str, settings: dict | None = None) -> str:
    settings = settings or {}
    shop = escape(str(settings.get("shop_name", "Boutique Senegal")))
    phone = escape(str(settings.get("phone", "")))
    address = escape(str(settings.get("address", "")))
    logo_url = escape(str(settings.get("logo_url", "")), quote=True)
    footer = escape(str(settings.get("receipt_footer", "Merci pour votre achat !")))
    contact = "<br>".join(value for value in (address, phone) if value)
    logo = f"<p><img src='{logo_url}' alt='Logo' style='max-width:90px;max-height:70px'></p>" if logo_url else ""
    lines = "".join(f"<tr><td>{escape(str(item['name']))} x{item['quantity']}</td><td>{item['quantity'] * item['sale_price']:,.0f} FCFA</td></tr>" for item in cart)
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>body{{font-family:Arial;max-width:320px;margin:auto}}h2,p{{text-align:center}}table{{width:100%;border-collapse:collapse}}td{{padding:5px;border-bottom:1px dashed #aaa}}.total{{font-size:18px;font-weight:bold}}</style></head><body>{logo}<h2>{shop}</h2><p>{contact}</p><p>Ticket #{ticket}<br>{datetime.now():%d/%m/%Y %H:%M}<br>Vendeur: {escape(seller)}<br>Client: {escape(client)}</p><table>{lines}</table><p>Sous-total: {gross:,.0f} FCFA<br>Reduction: {discount:,.0f} FCFA</p><p class='total'>TOTAL: {total:,.0f} FCFA</p><p>Verse: {paid:,.0f} FCFA<br>Monnaie: {paid-total:,.0f} FCFA<br>Paiement: {escape(payment)}</p><p>{footer}</p></body></html>"""


def make_receipt_pdf(ticket: int, cart: list[dict], seller: str, client: str, gross: float, discount: float, total: float, paid: float, payment: str, settings: dict | None = None) -> bytes:
    from reportlab.lib.pagesizes import A6
    from reportlab.pdfgen import canvas
    settings = settings or {}
    output = BytesIO(); pdf = canvas.Canvas(output, pagesize=A6); width, height = A6; y = height - 28
    pdf.setFont("Helvetica-Bold", 14); pdf.drawCentredString(width/2, y, str(settings.get("shop_name", "Boutique Senegal"))); y -= 18
    pdf.setFont("Helvetica", 8)
    for value in (settings.get("address", ""), settings.get("phone", ""), f"Ticket #{ticket} - {datetime.now():%d/%m/%Y %H:%M}", f"Vendeur: {seller}", f"Client: {client}"):
        if value: pdf.drawCentredString(width/2, y, str(value)); y -= 11
    y -= 4
    for item in cart:
        pdf.drawString(18, y, f"{item['name']} x{item['quantity']}"); pdf.drawRightString(width-18, y, f"{item['quantity']*item['sale_price']:,.0f}"); y -= 12
    y -= 4; pdf.line(18,y,width-18,y); y -= 14
    for label,value in (("Sous-total",gross),("Reduction",discount),("TOTAL",total),("Verse",paid),("Monnaie",paid-total)):
        pdf.drawString(18,y,label); pdf.drawRightString(width-18,y,f"{value:,.0f} FCFA"); y -= 12
    pdf.drawCentredString(width/2,y-4,f"Paiement: {payment}"); y -= 24
    pdf.drawCentredString(width/2,y,str(settings.get("receipt_footer", "Merci pour votre achat !")))
    pdf.save(); return output.getvalue()
