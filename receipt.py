from __future__ import annotations
from datetime import datetime
from html import escape
from io import BytesIO

import pandas as pd

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


def make_inventory_pdf(stock: pd.DataFrame, settings: dict | None = None) -> bytes:
    """Create an A4 inventory worksheet ready to print and fill by hand."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    settings = settings or {}
    output = BytesIO()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("InventoryTitle", parent=styles["Title"], alignment=TA_CENTER, fontName="Helvetica-Bold", fontSize=16, leading=19, textColor=colors.HexColor("#12372A"))
    small = ParagraphStyle("InventorySmall", parent=styles["Normal"], fontSize=8, leading=10)
    product_style = ParagraphStyle("InventoryProduct", parent=small, fontSize=8.5, leading=10)
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=12*mm, leftMargin=12*mm, topMargin=13*mm, bottomMargin=13*mm, title="Fiche d'inventaire")
    shop = escape(str(settings.get("shop_name", "Boutique Senegal")))
    address = escape(str(settings.get("address", "")))
    phone = escape(str(settings.get("phone", "")))
    story = [Paragraph(shop, title_style), Spacer(1, 2*mm), Paragraph("FICHE D'INVENTAIRE PHYSIQUE", ParagraphStyle("InventorySubtitle", parent=styles["Heading2"], alignment=TA_CENTER, fontSize=11, leading=14))]
    contact = " - ".join(value for value in (address, phone) if value)
    if contact:
        story.append(Paragraph(contact, ParagraphStyle("InventoryContact", parent=small, alignment=TA_CENTER)))
    story.extend([Spacer(1, 4*mm), Paragraph(f"Date : {datetime.now():%d/%m/%Y} &nbsp;&nbsp;&nbsp;&nbsp; Responsable : ______________________________", styles["Normal"]), Spacer(1, 4*mm)])

    rows = [["N°", "Produit", "Catégorie", "Code-barres", "Stock\nsystème", "Stock\ncompté", "Écart", "Observation"]]
    for index, record in stock.reset_index(drop=True).iterrows():
        rows.append([
            str(index + 1),
            Paragraph(escape(str(record.get("Produit", ""))), product_style),
            Paragraph(escape(str(record.get("Categorie", "") or "")), small),
            Paragraph(escape(str(record.get("Code_barres", "") or "")), small),
            str(int(record.get("Stock", 0))), "", "", "",
        ])
    table = Table(rows, colWidths=[9*mm, 39*mm, 25*mm, 31*mm, 18*mm, 18*mm, 14*mm, 32*mm], repeatRows=1, rowHeights=[11*mm] + [10*mm] * max(1, len(rows)-1))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#12372A")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("ALIGN", (0,0), (0,-1), "CENTER"),
        ("ALIGN", (4,1), (6,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#777777")),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F3F7F4")]),
        ("LEFTPADDING", (0,0), (-1,-1), 3),
        ("RIGHTPADDING", (0,0), (-1,-1), 3),
    ]))
    story.append(table)

    def footer(canvas, doc):
        canvas.saveState(); canvas.setFont("Helvetica", 8); canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(12*mm, 7*mm, "Boutique Senegal - Inventaire physique")
        canvas.drawRightString(A4[0]-12*mm, 7*mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
