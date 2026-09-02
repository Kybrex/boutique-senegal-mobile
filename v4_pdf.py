"""Documents d'impression de Boutique Senegal V4."""
from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO

import pandas as pd


def _money(value) -> str:
    return f"{float(value or 0):,.0f} FCFA".replace(",", " ")


def _footer(canvas, doc) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    canvas.saveState(); canvas.setFillColor(colors.HexColor("#666666")); canvas.setFont("Helvetica", 8)
    canvas.drawString(12*mm, 8*mm, "Boutique Senegal V4")
    canvas.drawRightString(A4[0]-12*mm, 8*mm, f"Page {doc.page}"); canvas.restoreState()


def make_barcode_labels_pdf(products: pd.DataFrame, settings: dict | None = None) -> bytes:
    """Planche A4 de 24 étiquettes avec Code 128, nom et prix."""
    from reportlab.graphics.barcode import code128
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Flowable, SimpleDocTemplate, Table, TableStyle

    settings=settings or {}; output=BytesIO()
    doc=SimpleDocTemplate(output,pagesize=A4,leftMargin=7*mm,rightMargin=7*mm,topMargin=8*mm,bottomMargin=8*mm,title="Étiquettes produits")
    class Label(Flowable):
        def __init__(self,row): super().__init__(); self.row=row; self.width=63*mm; self.height=32*mm
        def draw(self):
            name=str(self.row.get("Produit", ""))[:35]; barcode=str(self.row.get("Code_barres", "") or self.row.get("id", "")); price=_money(self.row.get("Vente",0))
            c=self.canv; c.setStrokeColor(colors.HexColor("#BBBBBB")); c.rect(0,0,self.width,self.height)
            c.setFont("Helvetica-Bold",8); c.drawCentredString(self.width/2,self.height-7*mm,name)
            if barcode:
                symbol=code128.Code128(barcode,barHeight=10*mm,barWidth=.28*mm); symbol.drawOn(c,(self.width-symbol.width)/2,7*mm)
                c.setFont("Helvetica",6); c.drawCentredString(self.width/2,4*mm,barcode)
            c.setFont("Helvetica-Bold",9); c.drawCentredString(self.width/2,1.3*mm,price)
    cells=[Label(r) for _,r in products.iterrows()]
    while len(cells)%3: cells.append("")
    rows=[cells[i:i+3] for i in range(0,len(cells),3)] or [[""]]
    table=Table(rows,colWidths=[65*mm]*3,rowHeights=[34*mm]*len(rows)); table.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ALIGN",(0,0),(-1,-1),"CENTER")]))
    doc.build([table]); return output.getvalue()


def make_statement_pdf(title: str, party: dict, rows: pd.DataFrame, settings: dict | None = None) -> bytes:
    """Relevé client ou fournisseur imprimable."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    settings=settings or {}; output=BytesIO(); styles=getSampleStyleSheet(); green=colors.HexColor("#12372A")
    doc=SimpleDocTemplate(output,pagesize=A4,leftMargin=12*mm,rightMargin=12*mm,topMargin=12*mm,bottomMargin=16*mm,title=title)
    name=party.get("Client",party.get("Fournisseur",party.get("name",""))); phone=party.get("Telephone",party.get("phone",""))
    story=[Paragraph(escape(str(settings.get("shop_name","Boutique Senegal"))),ParagraphStyle("shop",parent=styles["Title"],textColor=green,alignment=TA_CENTER)),Paragraph(escape(title.upper()),ParagraphStyle("head",parent=styles["Heading2"],alignment=TA_CENTER)),Spacer(1,4*mm),Paragraph(f"<b>Compte :</b> {escape(str(name))} &nbsp;&nbsp; <b>Téléphone :</b> {escape(str(phone or ''))}",styles["Normal"]),Paragraph(f"Édité le {datetime.now():%d/%m/%Y à %H:%M}",styles["Normal"]),Spacer(1,5*mm)]
    columns=list(rows.columns); data=[columns]
    for _,row in rows.iterrows():
        data.append([escape(str(row[c])) if not isinstance(row[c],float) else _money(row[c]) for c in columns])
    if not columns: data=[["Aucun mouvement"]]
    widths=[(A4[0]-24*mm)/max(1,len(data[0]))]*len(data[0]); table=Table(data,colWidths=widths,repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),green),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),7.5),("GRID",(0,0),(-1,-1),.35,colors.HexColor("#999999")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F3F7F4")]),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story.append(table); doc.build(story,onFirstPage=_footer,onLaterPages=_footer); return output.getvalue()


def make_catalog_pdf(products: pd.DataFrame, settings: dict | None = None) -> bytes:
    """Catalogue prix public avec deux produits par ligne."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    settings=settings or {}; output=BytesIO(); styles=getSampleStyleSheet(); green=colors.HexColor("#12372A")
    doc=SimpleDocTemplate(output,pagesize=A4,leftMargin=12*mm,rightMargin=12*mm,topMargin=12*mm,bottomMargin=16*mm,title="Catalogue produits")
    story=[Paragraph(escape(str(settings.get("shop_name","Boutique Senegal"))),ParagraphStyle("shop",parent=styles["Title"],textColor=green,alignment=TA_CENTER)),Paragraph("CATALOGUE PRODUITS",ParagraphStyle("sub",parent=styles["Heading2"],alignment=TA_CENTER)),Paragraph(escape(str(settings.get("phone", ""))),ParagraphStyle("contact",parent=styles["Normal"],alignment=TA_CENTER)),Spacer(1,6*mm)]
    cards=[]
    for _,r in products.iterrows():
        text=f"<b>{escape(str(r.get('Produit','')))}</b><br/>{escape(str(r.get('Categorie','') or ''))}<br/><font color='#12372A' size='13'><b>{_money(r.get('Vente',0))}</b></font>"
        cards.append(Paragraph(text,ParagraphStyle("card",parent=styles["Normal"],fontSize=10,leading=16,spaceAfter=4)))
    while len(cards)%2: cards.append("")
    rows=[cards[i:i+2] for i in range(0,len(cards),2)] or [[Paragraph("Aucun produit",styles["Normal"]),""]]
    table=Table(rows,colWidths=[91*mm,91*mm]); table.setStyle(TableStyle([("BOX",(0,0),(-1,-1),.6,colors.HexColor("#AAAAAA")),("INNERGRID",(0,0),(-1,-1),.4,colors.HexColor("#DDDDDD")),("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#F8FBF9")),("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),8*mm),("BOTTOMPADDING",(0,0),(-1,-1),8*mm),("LEFTPADDING",(0,0),(-1,-1),5*mm)])); story.append(table)
    doc.build(story,onFirstPage=_footer,onLaterPages=_footer); return output.getvalue()
