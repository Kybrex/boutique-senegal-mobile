from datetime import date
from io import BytesIO
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import pandas as pd
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest
import sales_insights as insights
import sales_insights_pdf as pdf
from test_sales_insights import sample

START, END = date(2026,10,1), date(2026,10,3)

def content(data):
    reader = PdfReader(BytesIO(data))
    return reader, '\n'.join(page.extract_text() or '' for page in reader.pages)

class PdfTests(TestCase):
    def test_filtered_list_content(self):
        rows = insights.filter_sales(sample(), 'emilie')
        reader, text = content(pdf.sales_pdf(rows, START, END, filters='Recherche : emilie'))
        self.assertIn('Émilie', text)
        self.assertNotIn('Moussa', text)
        self.assertIn('Recherche : emilie', text)
        self.assertIn('Payée', text)
        self.assertEqual(len(reader.pages), 1)
    def test_dashboard_comparison_and_zero_day(self):
        current = insights.summarize(sample(), START, END)
        previous = insights.summarize(pd.DataFrame(), date(2026,9,28), date(2026,9,30))
        _, text = content(pdf.dashboard_pdf(current, previous, START, END))
        for value in ('6 000', '4 500', '28/09/2026', '02/10/2026', 'Modes de paiement', 'Awa'):
            self.assertIn(value, text)
        self.assertIn('mouvements de caisse', text)
    def test_empty_list_and_dashboard(self):
        _, text = content(pdf.sales_pdf(pd.DataFrame(), START, END))
        self.assertIn('Aucune donnée', text)
        empty = insights.summarize(pd.DataFrame(), START, END)
        self.assertTrue(pdf.dashboard_pdf(empty, empty, START, END).startswith(b'%PDF'))
    def test_long_list_repeats_headers_and_preserves_last_row(self):
        rows = pd.concat([sample().assign(Ticket=100+i, Client='Client avec un nom long & détails <confidentiels>') for i in range(80)], ignore_index=True)
        reader, text = content(pdf.sales_pdf(rows, START, END))
        self.assertGreater(len(reader.pages), 2)
        self.assertIn('179', text)
        for page in reader.pages[1:]: self.assertIn('Client / vendeur', page.extract_text())
    def test_ui_downloads_work_after_filter_change(self):
        source = '''
from datetime import date
import sales_insights_ui as ui
from test_sales_insights import sample
rows = ui.filters(sample(), 'test')
ui.sales_export(rows, date(2026,10,1), date(2026,10,3), 'test')
ui.dashboard(date(2026,10,1), date(2026,10,3), 'chart')
'''
        with patch('db.report', return_value=sample()), patch('db.v2_ready', return_value=False):
            app = AppTest.from_string(source, default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.get('download_button')), 3)
            app.text_input[0].set_value('inexistant').run()
            self.assertFalse(app.exception)

if __name__ == '__main__':
    import unittest
    unittest.main()
