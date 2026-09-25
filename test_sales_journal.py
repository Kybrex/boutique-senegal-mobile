"""Exercise calendar grouping, seller totals and the generated PDFs."""
from datetime import date
from io import BytesIO

import pandas as pd
from pypdf import PdfReader

from sales_journal import dashboard_pdf, journal_pdf, journal_rows, journal_summary, period_bounds


assert period_bounds("Semaine", date(2026, 9, 25)) == (date(2026, 9, 21), date(2026, 9, 27))
assert period_bounds("Mois", date(2026, 12, 25)) == (date(2026, 12, 1), date(2026, 12, 31))
assert period_bounds("Mois", date(2024, 2, 15)) == (date(2024, 2, 1), date(2024, 2, 29))

sales = pd.DataFrame([
    {"Ticket": 1, "Date": "2026-09-25T10:00:00", "Vendeur": "Awa", "Client": "Client", "Total": 1200, "Reduction": 100, "Encaisse": 800, "Paiement": "Wave"},
    {"Ticket": 2, "Date": "2026-09-25T11:00:00", "Vendeur": "Moussa", "Client": "Comptant", "Total": 2000, "Reduction": 0, "Encaisse": 2000, "Paiement": "Espèces"},
])
filtered = journal_rows(sales, "Awa")
assert len(filtered) == 1 and filtered.iloc[0].Ticket == 1
summary = journal_summary(journal_rows(sales))
assert summary.Tickets.sum() == 2 and summary.Ventes.sum() == 3200 and summary.Reste.sum() == 400

for pdf in (
    dashboard_pdf(date(2026, 9, 25), 3200, 2, pd.DataFrame([{"Produit": "Chargeur", "Stock": 1, "Minimum": 3}]), 500, pd.DataFrame()),
    journal_pdf(sales, "Jour", date(2026, 9, 25), date(2026, 9, 25), "Tous les vendeurs"),
    journal_pdf(journal_rows(pd.DataFrame()), "Mois", date(2026, 9, 1), date(2026, 9, 30), "Tous les vendeurs"),
):
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) >= 1 and "Boutique Senegal" in reader.pages[0].extract_text()

print("PASS: calendar periods, seller filtering, totals and dashboard/journal PDFs")
