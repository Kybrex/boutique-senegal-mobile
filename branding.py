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
