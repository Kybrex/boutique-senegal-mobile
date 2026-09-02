"""Documents PDF professionnels de Boutique Senegal V3."""
from __future__ import annotations

from datetime import date, datetime
from html import escape
from io import BytesIO

import pandas as pd


def _money(value: float) -> str:
    return f"{float(value):,.0f} FCFA".replace(",", " ")


def _footer(canvas, doc) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    canvas.saveState(); canvas.setFont("Helvetica", 8); canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawString(15*mm, 8*mm, "Boutique Senegal")
    canvas.drawRightString(A4[0]-15*mm, 8*mm, f"Page {doc.page}")
    canvas.restoreState()


def make_business_document_pdf(document: dict, items: pd.DataFrame, settings: dict | None = None) -> bytes:
    """Create a quotation, invoice or delivery-note PDF."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    settings = settings or {}; output = BytesIO(); styles = getSampleStyleSheet()
    kind = str(document.get("Type", document.get("document_type", "DEVIS"))).upper()
    titles = {"DEVIS":"DEVIS", "FACTURE":"FACTURE", "BON_LIVRAISON":"BON DE LIVRAISON", "BON_COMMANDE":"BON DE COMMANDE FOURNISSEUR"}
    title = titles.get(kind, kind.replace("_", " "))
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=15*mm, rightMargin=15*mm, topMargin=14*mm, bottomMargin=16*mm, title=title)
    green=colors.HexColor("#12372A"); small=ParagraphStyle("small",parent=styles["Normal"],fontSize=9,leading=12)
    story=[Paragraph(escape(str(settings.get("shop_name","Boutique Senegal"))),ParagraphStyle("shop",parent=styles["Title"],textColor=green,fontSize=18,leading=22)),Spacer(1,2*mm)]
    contact=" - ".join(escape(str(v)) for v in (settings.get("address",""),settings.get("phone","")) if v)
    if contact: story.append(Paragraph(contact,small))
    story.extend([Spacer(1,7*mm),Paragraph(title,ParagraphStyle("doctype",parent=styles["Heading1"],alignment=TA_RIGHT,textColor=green,fontSize=20))])
    number=document.get("id",document.get("Numero","")); created=str(document.get("created_at",document.get("Date",date.today().isoformat())))[:10]
    client=escape(str(document.get("Client",document.get("client","Comptant")) or "Comptant")); valid=document.get("valid_until",document.get("Validite","")) or ""
    meta=[["Numéro",f"#{number}"],["Date",created],["Fournisseur" if kind=="BON_COMMANDE" else "Client",Paragraph(client,small)]]
    if kind=="DEVIS" and valid: meta.append(["Valable jusqu'au",str(valid)[:10]])
    mt=Table(meta,colWidths=[40*mm,80*mm],hAlign="RIGHT"); mt.setStyle(TableStyle([("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),9),("BOTTOMPADDING",(0,0),(-1,-1),5)])); story.extend([mt,Spacer(1,7*mm)])
    rows=[["Produit","Quantité","Prix unitaire","Total"]]
    for _,r in items.iterrows():
        name=r.get("Produit",r.get("product_name","")); qty=int(r.get("Quantite",r.get("quantity",0))); price=float(r.get("Prix",r.get("unit_price",0)))
        rows.append([Paragraph(escape(str(name)),small),str(qty),_money(price),_money(qty*price)])
    table=Table(rows,colWidths=[82*mm,24*mm,35*mm,39*mm],repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),green),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("GRID",(0,0),(-1,-1),.4,colors.HexColor("#888888")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ALIGN",(1,1),(-1,-1),"RIGHT"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F3F7F4")]),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)])); story.extend([table,Spacer(1,6*mm)])
    total=float(document.get("Total",document.get("total",sum(float(r.get("quantity",0))*float(r.get("unit_price",0)) for _,r in items.iterrows()))))
    totals=Table([[Paragraph("TOTAL",ParagraphStyle("total",parent=styles["Normal"],fontName="Helvetica-Bold",alignment=TA_RIGHT)),Paragraph(_money(total),ParagraphStyle("money",parent=styles["Normal"],fontName="Helvetica-Bold",alignment=TA_RIGHT,textColor=green,fontSize=13))]],colWidths=[130*mm,50*mm]); story.append(totals)
    notes=str(document.get("notes",document.get("Notes","")) or "")
    if notes: story.extend([Spacer(1,8*mm),Paragraph("Notes",styles["Heading3"]),Paragraph(escape(notes),small)])
    story.extend([Spacer(1,15*mm),Paragraph("Signature / Cachet : _________________________________",small)])
    doc.build(story,onFirstPage=_footer,onLaterPages=_footer); return output.getvalue()


def make_product_list_pdf(products: pd.DataFrame, settings: dict | None = None) -> bytes:
    """Create an A4 printable product catalogue/stock list."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    settings=settings or {}; output=BytesIO(); styles=getSampleStyleSheet(); green=colors.HexColor("#12372A")
    doc=SimpleDocTemplate(output,pagesize=A4,leftMargin=12*mm,rightMargin=12*mm,topMargin=13*mm,bottomMargin=16*mm,title="Liste des produits")
    story=[Paragraph(escape(str(settings.get("shop_name","Boutique Senegal"))),ParagraphStyle("title",parent=styles["Title"],alignment=TA_CENTER,textColor=green)),Paragraph("LISTE DES PRODUITS",ParagraphStyle("sub",parent=styles["Heading2"],alignment=TA_CENTER)),Paragraph(f"Imprimée le {datetime.now():%d/%m/%Y à %H:%M}",ParagraphStyle("date",parent=styles["Normal"],alignment=TA_CENTER)),Spacer(1,5*mm)]
    small=ParagraphStyle("cell",parent=styles["Normal"],fontSize=7.5,leading=9)
    rows=[["N°","Produit","Catégorie","Code-barres","Achat","Vente","Stock","Minimum"]]
    for i,(_,r) in enumerate(products.reset_index(drop=True).iterrows(),1): rows.append([str(i),Paragraph(escape(str(r.get("Produit",""))),small),Paragraph(escape(str(r.get("Categorie","") or "")),small),str(r.get("Code_barres","") or ""),_money(r.get("Achat",0)),_money(r.get("Vente",0)),str(int(r.get("Stock",0))),str(int(r.get("Minimum",0)))])
    table=Table(rows,colWidths=[8*mm,42*mm,27*mm,32*mm,25*mm,25*mm,13*mm,16*mm],repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),green),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),7),("GRID",(0,0),(-1,-1),.35,colors.HexColor("#888888")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ALIGN",(4,1),(-1,-1),"RIGHT"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F3F7F4")]),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)])); story.append(table)
    doc.build(story,onFirstPage=_footer,onLaterPages=_footer); return output.getvalue()
