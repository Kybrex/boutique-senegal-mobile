"""Printable snapshots of filtered sales and period analytics."""
from html import escape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, Spacer, CondPageBreak
from reportlab.graphics.shapes import Drawing, Line, PolyLine, String
from reportlab.lib import colors
from sales_journal import _pdf, _table
import sales_insights as insights

NOTE = 'Les montants payés et les restes reflètent l’état actuel des ventes, y compris les paiements complémentaires. Ils ne représentent pas les mouvements de caisse de la période.'

def money(value):
    return f'{value:,.0f}'.replace(',', ' ')

def section(title, headers, rows, widths):
    styles = getSampleStyleSheet()
    heading = Paragraph(escape(title), styles['Heading3'])
    heading.keepWithNext = False
    body = _table(headers, rows, widths) if rows else Paragraph('Aucune donnée.', styles['Normal'])
    return [CondPageBreak(115 if rows else 50), Spacer(1, 12), heading, body]

def sales_pdf(sales, start, end, title='Liste des ventes', filters='', settings=None):
    rows = insights.prepare(sales)
    styles = getSampleStyleSheet()
    content = [Paragraph(escape(filters or 'Toutes les ventes de la période'), styles['Normal']), Spacer(1, 10)]
    content += section('Synthèse', ['Indicateur', 'Valeur'], [
        ['Tickets', len(rows)], ['Ventes (FCFA)', money(rows.Total.sum())],
        ['Montants payés (FCFA)', money(rows.Encaisse.sum())], ['Reste (FCFA)', money(rows.Reste.sum())],
    ], [300, 230])
    content += [Spacer(1, 10), Paragraph(escape(NOTE), styles['Normal'])]
    details = [[int(r.Ticket), str(r.Date)[:10], f'{r.Client} / {r.Vendeur}', r.Paiement, money(r.Total), money(r.Encaisse), money(r.Reste), r.Etat] for r in rows.itertuples(index=False)]
    content += section('Détail des ventes (FCFA)', ['N°', 'Date', 'Client / vendeur', 'Mode', 'Total', 'Payé', 'Reste', 'État'], details, [30, 65, 110, 55, 65, 65, 65, 75])
    return _pdf(title, f'Du {start:%d/%m/%Y} au {end:%d/%m/%Y}', content, settings)

def daily_chart(daily):
    """Vector chart; values are also included in the following daily table."""
    drawing = Drawing(530, 165)
    x0, y0, width, height = 55, 28, 460, 115
    maximum = max(float(daily.max()), 1)
    drawing.add(Line(x0, y0, x0 + width, y0, strokeColor=colors.grey))
    for fraction in (0, .5, 1):
        y = y0 + height * fraction
        drawing.add(Line(x0, y, x0+width, y, strokeColor=colors.HexColor('#DDE5DF')))
        drawing.add(String(0, y-3, money(maximum*fraction), fontName='Helvetica', fontSize=8))
    points = []
    for i, value in enumerate(daily):
        points.extend([x0 + width*i/max(len(daily)-1, 1), y0 + height*float(value)/maximum])
    if len(points) == 2: points += [x0 + width, points[1]]
    drawing.add(PolyLine(points, strokeColor=colors.HexColor('#12372A'), strokeWidth=1.5))
    drawing.add(String(x0, 10, daily.index[0].strftime('%d/%m/%Y'), fontSize=8))
    drawing.add(String(x0+width, 10, daily.index[-1].strftime('%d/%m/%Y'), fontSize=8, textAnchor='end'))
    drawing.add(String(x0, 153, 'Ventes quotidiennes (FCFA)', fontSize=9))
    return drawing

def dashboard_pdf(current, previous, start, end, settings=None):
    prior_start, prior_end = insights.previous_period(start, end)
    styles = getSampleStyleSheet()
    content = section('Indicateurs', ['Indicateur', 'Période choisie', 'Période précédente'], [
        ['Chiffre d’affaires (FCFA)', money(current['total']), money(previous['total'])],
        ['Tickets', current['tickets'], previous['tickets']],
        ['Panier moyen (FCFA)', money(current['average']), money(previous['average'])],
        ['Montants payés (FCFA)', money(current['paid']), money(previous['paid'])],
        ['Reste (FCFA)', money(current['remaining']), money(previous['remaining'])],
    ], [230, 150, 150])
    content += [Spacer(1, 8), Paragraph(f'Comparaison avec le {prior_start:%d/%m/%Y} au {prior_end:%d/%m/%Y}, de même durée.', styles['Normal']), Spacer(1, 8), Paragraph(escape(NOTE), styles['Normal']), Spacer(1, 10), daily_chart(current['daily'])]
    content += section('Modes de paiement', ['Mode', 'Tickets', 'Ventes (FCFA)', 'Payé (FCFA)'], [[r.Paiement, r.Tickets, money(r.Ventes), money(r.Montant_paye)] for r in current['payments'].itertuples(index=False)], [170, 70, 145, 145])
    content += section('Ventes par vendeur', ['Vendeur', 'Tickets', 'Ventes (FCFA)'], [[r.Vendeur, r.Tickets, money(r.Ventes)] for r in current['sellers'].itertuples(index=False)], [260, 90, 180])
    content += section('Détail quotidien', ['Jour', 'Ventes (FCFA)'], [[day.strftime('%d/%m/%Y'), money(value)] for day, value in current['daily'].items()], [260, 270])
    return _pdf('Analyse du tableau de bord', f'Du {start:%d/%m/%Y} au {end:%d/%m/%Y}', content, settings)
