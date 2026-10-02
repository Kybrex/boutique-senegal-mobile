from datetime import date
from unittest import TestCase
from unittest.mock import patch
import pandas as pd
import cloud_db
import sales_insights as insights
from streamlit.testing.v1 import AppTest

def sample():
    return pd.DataFrame([
        dict(Ticket=12, Date='2026-10-01T23:20:00+00:00', Client='Émilie', Vendeur='Awa', Total=1000, Encaisse=1000, Reduction=0, Paiement='Wave'),
        dict(Ticket=13, Date='2026-10-01', Client='Moussa', Vendeur='Awa', Total=2000, Encaisse=500, Reduction=0, Paiement='Espèces'),
        dict(Ticket=14, Date='2026-10-03', Client='Fatou', Vendeur='Ali', Total=3000, Encaisse=0, Reduction=0, Paiement='Crédit'),
    ])

class InsightsTests(TestCase):
    def test_search_and_combined_filters(self):
        self.assertEqual(insights.filter_sales(sample(), 'emilie').Ticket.tolist(), [12])
        self.assertEqual(insights.filter_sales(sample(), '#13', 'Partiellement payée', 'Espèces', 'Awa').Ticket.tolist(), [13])
        self.assertTrue(insights.filter_sales(sample(), state='Non payée', seller='Awa').empty)
    def test_payment_states_and_remainders(self):
        rows = insights.prepare(sample())
        self.assertEqual(rows.Reste.tolist(), [0, 1500, 3000])
        self.assertEqual(rows.Etat.tolist(), insights.STATES[1:])
    def test_daily_zero_days_and_aggregates(self):
        data = insights.summarize(sample(), date(2026,10,1), date(2026,10,3))
        self.assertEqual(data['daily'].tolist(), [3000, 0, 3000])
        self.assertEqual((data['total'],data['paid'],data['remaining'],data['average']), (6000,1500,4500,2000))
        self.assertEqual(data['payments'].Ventes.sum(), 6000)
    def test_empty_data(self):
        data = insights.summarize(pd.DataFrame(), date(2026,10,1), date(2026,10,1))
        self.assertEqual(data['average'], 0)
        self.assertEqual(data['daily'].tolist(), [0])
        self.assertTrue(insights.filter_sales(pd.DataFrame(), 'client').empty)
    def test_previous_period_crosses_year(self):
        self.assertEqual(insights.previous_period(date(2026,1,1),date(2026,1,3)), (date(2025,12,29),date(2025,12,31)))
    def test_cloud_pagination(self):
        rows = [dict(id=i,created_at='2026-10-01',total=100,discount=0,paid=50,payment_method='Wave') for i in range(1201)]
        class Query:
            def select(self,*a): return self
            def gte(self,*a): return self
            def lt(self,*a): return self
            def order(self,*a,**k): return self
            def range(self,lo,hi): self.bounds=(lo,hi); return self
            def execute(self):
                lo,hi=self.bounds
                return type('Response',(),{'data':rows[lo:hi+1]})()
        with patch.object(cloud_db,'_table',side_effect=lambda _:Query()):
            report=cloud_db.report(date(2026,10,1),date(2026,10,1))
        self.assertEqual(len(report),1201)
        self.assertEqual(report.Total.sum(),120100)
    def test_ui_filters_and_dashboard(self):
        source = '''
from datetime import date
import sales_insights_ui as ui
import streamlit as st
from test_sales_insights import sample
rows=ui.filters(sample(), 'test')
st.dataframe(rows)
ui.dashboard(date(2026,10,1), date(2026,10,3), 'test')
'''
        with patch('db.report', return_value=sample()):
            app=AppTest.from_string(source,default_timeout=20).run()
            self.assertFalse(app.exception)
            app.text_input[0].set_value('emilie').run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.dataframe[0].value),1)
