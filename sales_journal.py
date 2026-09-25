"""Printable dashboard and sales journal shared by the mobile interface."""
from __future__ import annotations

from datetime import date, timedelta
from html import escape
from io import BytesIO

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from branding import build_document, logo_flowables


def period_bounds(period: str, reference: date) -> tuple[date, date]:
    if period == "Jour":
        return reference, reference
    if period == "Semaine":
        start = reference - timedelta(days=reference.weekday())
        return start, start + timedelta(days=6)
    if period == "Mois":
        start = reference.replace(day=1)
        next_month = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
        return start, next_month - timedelta(days=1)
    raise ValueError("Période inconnue.")


def journal_rows(sales: pd.DataFrame, seller: str = "Tous les vendeurs") -> pd.DataFrame:
    columns = ["Ticket", "Date", "Vendeur", "Client", "Total", "Reduction", "Encaisse", "Paiement"]
    if sales.empty:
        return pd.DataFrame(columns=columns)
    filtered = sales.loc[sales["Vendeur"].eq(seller)].copy() if seller != "Tous les vendeurs" else sales.copy()
    return filtered.loc[:, columns]


def journal_summary(sales: pd.DataFrame) -> pd.DataFrame:
    if sales.empty:
        return pd.DataFrame(columns=["Vendeur", "Tickets", "Ventes", "Encaissé", "Reste"])
    grouped = sales.groupby("Vendeur", dropna=False).agg(Tickets=("Ticket", "count"), Ventes=("Total", "sum"), **{"Encaissé": ("Encaisse", "sum")}).reset_index()
    grouped["Reste"] = grouped["Ventes"] - grouped["Encaissé"]
    return grouped


def _table(headers: list[str], rows: list[list[object]], widths: list[float]) -> Table:
    styles = getSampleStyleSheet()
    header_style = ParagraphStyle("JournalHeader", parent=styles["BodyText"], textColor=colors.white)
    data = [[Paragraph(escape(str(value)), header_style) for value in headers]]
    data += [[Paragraph(escape(str(value)), styles["BodyText"]) for value in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12372A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F5F1")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#12372A")),
    ]))
    return table


def _pdf(title: str, subtitle: str, content: list, settings: dict | None = None) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, leftMargin=32, rightMargin=32, topMargin=28, bottomMargin=38, title=title)
    styles = getSampleStyleSheet()
    story = logo_flowables(85) + [Paragraph(escape(str((settings or {}).get("shop_name") or "Boutique Senegal")), styles["Heading1"]), Paragraph(escape(title), styles["Heading2"]), Paragraph(escape(subtitle), styles["Normal"]), Spacer(1, 14)] + content
    build_document(document, story, settings)
    return output.getvalue()


def dashboard_pdf(day: date, sales_total: float, tickets: int, alerts: pd.DataFrame, purchases: float, credits: pd.DataFrame, settings: dict | None = None) -> bytes:
    styles = getSampleStyleSheet()
    content = [_table(["Indicateur", "Valeur"], [["Ventes", f"{sales_total:,.0f} FCFA"], ["Tickets", tickets], ["Alertes de stock", len(alerts)], ["Achats de stock", f"{purchases:,.0f} FCFA"]], [250, 280]), Spacer(1, 14), Paragraph("Stock à surveiller", styles["Heading3"])]
    content.append(_table(["Produit", "Stock", "Minimum"], [[r.Produit, r.Stock, r.Minimum] for r in alerts.itertuples(index=False)] or [["Aucune alerte", "", ""]], [300, 100, 130]))
    content += [Spacer(1, 14), Paragraph("Échéances de crédits", styles["Heading3"])]
    if credits.empty:
        content.append(Paragraph("Aucune échéance à signaler.", styles["Normal"]))
    else:
        content.append(_table(["Client", "Échéance", "Reste"], [[str(r.get("Client", "")), str(r.get("Echeance", r.get("Date", ""))), f'{float(r.get("Reste", 0)):,.0f} FCFA'] for _, r in credits.iterrows()], [200, 150, 180]))
    return _pdf("Tableau de bord", f"Situation du {day:%d/%m/%Y}", content, settings)


def journal_pdf(sales: pd.DataFrame, period: str, start: date, end: date, seller: str, settings: dict | None = None) -> bytes:
    styles = getSampleStyleSheet()
    summary = journal_summary(sales)
    total = float(sales["Total"].sum()) if not sales.empty else 0.0
    paid = float(sales["Encaisse"].sum()) if not sales.empty else 0.0
    content = [Paragraph(f"{len(sales)} tickets · Ventes : {total:,.0f} FCFA · Encaissé : {paid:,.0f} FCFA · Reste : {total-paid:,.0f} FCFA", styles["Normal"]), Spacer(1, 12), Paragraph("Par vendeur", styles["Heading3"])]
    content.append(_table(["Vendeur", "Tickets", "Ventes", "Encaissé", "Reste"], [[r["Vendeur"], r["Tickets"], f'{r["Ventes"]:,.0f}', f'{r["Encaissé"]:,.0f}', f'{r["Reste"]:,.0f}'] for _, r in summary.iterrows()] or [["Aucune vente", "", "", "", ""]], [140, 55, 110, 110, 115]))
    content += [Spacer(1, 14), Paragraph("Détail des ventes", styles["Heading3"])]
    content.append(_table(["Ticket", "Date", "Vendeur", "Client", "Total", "Encaissé"], [[r.Ticket, str(r.Date)[:16].replace("T", " "), r.Vendeur, r.Client, f"{r.Total:,.0f}", f"{r.Encaisse:,.0f}"] for r in sales.itertuples(index=False)] or [["Aucune vente", "", "", "", "", ""]], [42, 102, 95, 95, 98, 98]))
    return _pdf("Journal des ventes", f"{period} · du {start:%d/%m/%Y} au {end:%d/%m/%Y} · {seller}", content, settings)
