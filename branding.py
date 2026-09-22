"""Shared local logo for the interface and printable documents."""
from pathlib import Path
from base64 import b64encode

LOGO_PATH = Path(__file__).resolve().parent / "assets" / "logo.jpg"

def logo_data_uri():
    return "data:image/jpeg;base64," + b64encode(LOGO_PATH.read_bytes()).decode("ascii")

def logo_flowables(width=120):
    from reportlab.platypus import Image, Spacer
    image = Image(str(LOGO_PATH))
    image.drawHeight = width * image.imageHeight / image.imageWidth
    image.drawWidth = width
    image.hAlign = "CENTER"
    return [image, Spacer(1, 8)]

def build_document(document, story, settings=None):
    """Reserve space and repeat the shop contact details on every PDF page."""
    from html import escape
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph

    settings = settings or {}
    address = str(settings.get("address") or "").strip()
    phone = str(settings.get("phone") or "").strip()
    lines = []
    if address:
        lines.append(escape(address).replace("\n", "<br/>"))
    if phone:
        lines.append("Tél. : " + escape(phone))
    contact = Paragraph("<br/>".join(lines), ParagraphStyle(
        "ShopFooter", fontName="Helvetica", fontSize=8, leading=10,
        alignment=1, textColor=colors.HexColor("#555555"),
    )) if lines else None
    footer_height = contact.wrap(document.width, document.pagesize[1])[1] if contact else 0
    document.bottomMargin = max(document.bottomMargin, footer_height + 38)
    document._calc()

    def footer(canvas, doc):
        canvas.saveState()
        if contact:
            canvas.setStrokeColor(colors.HexColor("#CCCCCC"))
            canvas.setLineWidth(0.4)
            canvas.line(doc.leftMargin, footer_height + 27,
                        doc.pagesize[0] - doc.rightMargin, footer_height + 27)
            contact.drawOn(canvas, doc.leftMargin, 22)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawCentredString(doc.pagesize[0] / 2, 10, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
