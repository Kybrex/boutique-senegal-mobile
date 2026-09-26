"""Documents d'impression de Boutique Senegal V4."""
from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO

import pandas as pd
from branding import build_document, logo_flowables


def _money(value) -> str:
    return f"{float(value or 0):,.0f} FCFA".replace(",", " ")



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
    build_document(doc, [table], settings); return output.getvalue()


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
    story=logo_flowables() + [Paragraph(escape(str(settings.get("shop_name","Boutique Senegal"))),ParagraphStyle("shop",parent=styles["Title"],textColor=green,alignment=TA_CENTER)),Paragraph(escape(title.upper()),ParagraphStyle("head",parent=styles["Heading2"],alignment=TA_CENTER)),Spacer(1,4*mm),Paragraph(f"<b>Compte :</b> {escape(str(name))} &nbsp;&nbsp; <b>Téléphone :</b> {escape(str(phone or ''))}",styles["Normal"]),Paragraph(f"Édité le {datetime.now():%d/%m/%Y à %H:%M}",styles["Normal"]),Spacer(1,5*mm)]
    columns=list(rows.columns); data=[columns]
    for _,row in rows.iterrows():
        data.append([escape(str(row[c])) if not isinstance(row[c],float) else _money(row[c]) for c in columns])
    if not columns: data=[["Aucun mouvement"]]
    widths=[(A4[0]-24*mm)/max(1,len(data[0]))]*len(data[0]); table=Table(data,colWidths=widths,repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),green),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),7.5),("GRID",(0,0),(-1,-1),.35,colors.HexColor("#999999")),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F3F7F4")]),("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story.append(table); build_document(doc, story, settings); return output.getvalue()


def _catalog_photo(source):
    """Decode stored uploads or public image URLs; a broken photo is optional."""
    import base64
    from urllib.request import urlopen
    from PIL import Image, ImageOps

    limit = 10 * 1024 * 1024
    if not isinstance(source, str) or not source.strip():
        return None
    source = source.strip()
    try:
        if source.startswith('data:image/'):
            header, encoded = source.split(',', 1)
            if not header.endswith(';base64') or len(encoded) > limit * 4 // 3 + 4:
                return None
            data = base64.b64decode(encoded, validate=True)
        elif source.startswith(('https://', 'http://')):
            with urlopen(source, timeout=5) as response:
                data = response.read(limit + 1)
        else:
            return None
        if len(data) > limit:
            return None
        with Image.open(BytesIO(data)) as original:
            if original.width * original.height > 25_000_000:
                return None
            photo = ImageOps.exif_transpose(original)
            photo.thumbnail((800, 600))
            photo = photo.convert('RGBA')
            background = Image.new('RGB', photo.size, 'white')
            background.paste(photo, mask=photo.getchannel('A'))
            output = BytesIO()
            background.save(output, format='JPEG', quality=85)
            return output.getvalue()
    except Exception:
        return None


def make_catalog_pdf(products: pd.DataFrame, settings: dict | None = None, options: dict | None = None) -> bytes:
    """Catalogue prix public avec deux produits par ligne."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    settings=settings or {}; output=BytesIO(); styles=getSampleStyleSheet(); green=colors.HexColor("#12372A")
    doc=SimpleDocTemplate(output,pagesize=A4,leftMargin=12*mm,rightMargin=12*mm,topMargin=12*mm,bottomMargin=16*mm,title="Catalogue produits")
    options = options or {}
    story=logo_flowables() + [Paragraph(escape(str(settings.get("shop_name","Boutique Senegal"))),ParagraphStyle("shop",parent=styles["Title"],textColor=green,alignment=TA_CENTER)),Paragraph(escape(str(options.get('title') or 'CATALOGUE PRODUITS')),ParagraphStyle("sub",parent=styles["Heading2"],alignment=TA_CENTER)),Spacer(1,6*mm)]
    from catalog_options import prepare_catalog, order_link, whatsapp_number
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    options = options or {}
    products = prepare_catalog(products, options)
    show_prices = options.get('show_prices', True)
    if options.get('cover'):
        from reportlab.platypus import PageBreak
        center = ParagraphStyle('CoverText', parent=styles['Normal'], alignment=TA_CENTER, fontSize=12, leading=18)
        cover_story = [Spacer(1, 24*mm)] + logo_flowables(width=180)
        cover_story += [Spacer(1, 12*mm), Paragraph('Samaly Trading', ParagraphStyle('CoverBrand', parent=styles['Title'], textColor=green)),
                        Paragraph(escape(str(options.get('title') or 'Catalogue produits')), center), Spacer(1, 8*mm)]
        for value in (settings.get('shop_name'), settings.get('address'), settings.get('phone')):
            if value:
                cover_story.append(Paragraph(escape(str(value)).replace('\n','<br/>'), center))
        cover_story += [Spacer(1, 8*mm), Paragraph(f'{len(products)} produits sélectionnés', center)]
        if not show_prices:
            cover_story.append(Paragraph('Catalogue sans prix - Tarifs sur demande', center))
        cover_story.append(PageBreak())
        story = cover_story + story
    number = whatsapp_number(options.get('whatsapp', ''))
    link = order_link(number)
    if options.get('valid_until'):
        validity = datetime.fromisoformat(str(options['valid_until'])).strftime('%d/%m/%Y')
        label = 'Prix valables' if show_prices else 'Catalogue valable'
        story.append(Paragraph(f'{label} jusqu’au {validity}', styles['Normal']))
    if link:
        qr = QrCodeWidget(link)
        x1, y1, x2, y2 = qr.getBounds()
        size = 27 * mm
        drawing = Drawing(size, size, transform=[size/(x2-x1), 0, 0, size/(y2-y1), 0, 0])
        drawing.add(qr)
        contact = Paragraph(f'<b>Commandez sur WhatsApp : +{number}</b><br/>Scannez le QR code ou <link href="{escape(link, quote=True)}" color="#12372A"><u>cliquez ici pour commander</u></link>.<br/>Indiquez la référence et la quantité souhaitée.', styles['Normal'])
        banner = Table([[contact, drawing]], colWidths=[150*mm, 32*mm])
        banner.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
        story.extend([banner, Spacer(1, 4*mm)])
    delivery = []
    for key, label in [('delivery_zones','Zones'), ('delivery_fees','Frais'), ('delivery_times','Délais')]:
        value = str(options.get(key, '') or '').strip()
        if value:
            delivery.append(f'<b>{label} :</b> {escape(value).replace(chr(10), "<br/>")}')
    if delivery:
        from reportlab.platypus import KeepTogether
        story.append(KeepTogether([Paragraph('Conditions de livraison', styles['Heading2']), Paragraph('<br/>'.join(delivery), styles['Normal']), Spacer(1, 4*mm)]))
    from reportlab.platypus import Flowable
    from reportlab.lib.utils import ImageReader

    class Photo(Flowable):
        width = 80 * mm
        height = 48 * mm

        def __init__(self, data):
            super().__init__()
            self.width = 80 * mm
            self.height = 48 * mm
            self.data = data

        def draw(self):
            if self.data:
                self.canv.drawImage(ImageReader(BytesIO(self.data)), 0, 0,
                                    width=self.width, height=self.height,
                                    preserveAspectRatio=True, anchor='c', mask='auto')
            else:
                self.canv.setFillColor(colors.HexColor('#EEF2EF'))
                self.canv.rect(0, 0, self.width, self.height, fill=1, stroke=0)
                self.canv.setFillColor(colors.HexColor('#68756C'))
                self.canv.setFont('Helvetica', 9)
                self.canv.drawCentredString(self.width / 2, self.height / 2, 'Photo indisponible')

    cards=[]
    category = None
    def add_cards():
        from reportlab.platypus import KeepTogether
        if not cards:
            return
        if len(cards) % 2:
            cards.append('')
        for i in range(0, len(cards), 2):
            table = Table([cards[i:i+2]], colWidths=[91*mm]*2)
            table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,colors.HexColor('#DDDDDD')),('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#F8FBF9')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),5*mm),('BOTTOMPADDING',(0,0),(-1,-1),5*mm),('LEFTPADDING',(0,0),(-1,-1),5*mm)]))
            if i == 0:
                story.append(KeepTogether([Paragraph(escape(category), styles['Heading2']), table]))
            else:
                story.append(table)
        story.append(Spacer(1, 5*mm))
        cards.clear()
    photos = {}
    for _,r in products.iterrows():
        if category != r['Categorie']:
            add_cards()
            category = r['Categorie']
        source = r.get('Photo', '')
        source = source.strip() if isinstance(source, str) else ''
        if source not in photos:
            photos[source] = _catalog_photo(source)
        price = _money(r.get('Vente',0))
        if pd.notna(r.get('Promo')):
            price = f"<strike>{price}</strike><br/><font color='#B43D22'>PROMO : {_money(r['Promo'])}</font>"
        ref = escape(r['Reference'])
        text=f"<b>{escape(str(r.get('Produit','')))}</b><br/>Réf. : {ref}"
        for field, label in [('Description',''), ('Tailles','Tailles : '), ('Couleurs','Couleurs : ')]:
            if r[field]:
                text += '<br/>' + label + escape(r[field]).replace('\n', '<br/>')
        if show_prices:
            text += f"<br/><font color='#12372A' size='13'><b>{price}</b></font>"
        if link:
            item_link = order_link(number, f"Bonjour, je souhaite commander {r['Produit']} (réf. {r['Reference']}). Quantité : ")
            text += f'<br/><link href="{escape(item_link, quote=True)}" color="#12372A"><u>Commander sur WhatsApp</u></link>'
        cards.append([Photo(photos[source]), Spacer(1, 4*mm), Paragraph(text,ParagraphStyle("card",parent=styles["Normal"],fontSize=10,leading=16,spaceAfter=4))])
    add_cards()
    if products.empty:
        story.append(Paragraph('Aucun produit', styles['Normal']))
    build_document(doc, story, settings); return output.getvalue()
