from datetime import date
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import gc
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest
import db, cloud_db, business_features as features
import monthly_management as management
import monthly_management_pdf as pdf
import workflow_service as workflows

class MonthlyTests(TestCase):
    def setUp(self):
        self.folder=TemporaryDirectory();self.old_path=db.DB_PATH
        db.DB_PATH=Path(self.folder.name)/'test.db'
        self.mock=patch.object(cloud_db,'enabled',return_value=False);self.mock.start()
        db.init_db();db.create_user('admin','Admin','test-password','admin')
        self.user=db.authenticate('admin','test-password')
        db.create_seller_with_user('Seller','','','seller','test-password')
        db.add_client('Awa','771234567','','Dakar')
        db.add_product('Riz','Alimentaire',500,1000,20,2,None)
        db.add_product('Thé','Boissons',100,200,10,1,None)
        self.sale=db.save_sale([{'id':1,'quantity':2,'sale_price':1000}],1,1,500,'Espèces',200)[0]
        db.execute('UPDATE sales SET created_at=?, commission_amount=100 WHERE id=?',('2026-10-02',self.sale))
        db.add_expense('Transport',200)
        db.add_expense('Achat stock - Thé',500)
        db.execute('UPDATE expenses SET created_at=?',('2026-10-02',))
    def tearDown(self):
        db.DB_PATH=self.old_path;self.mock.stop();gc.collect();self.folder.cleanup()
    def test_month_bounds_leap_and_december(self):
        self.assertEqual(management.month_bounds(date(2024,2,10)),(date(2024,2,1),date(2024,2,29)))
        self.assertEqual(management.month_bounds(date(2026,12,31))[1],date(2026,12,31))
    def test_goal_saved_and_isolated_by_month(self):
        management.save_goal(date(2026,10,1),5000,self.user)
        self.assertEqual(management.goal(date(2026,10,25)),5000)
        self.assertEqual(management.goal(date(2026,11,1)),0)
        self.assertEqual(management.goal_progress(6000,5000),{'ratio':1,'percent':120,'remaining':0})
    def test_goal_permission_and_invalid_values(self):
        for value in (-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError): management.save_goal(date.today(),value,self.user)
        with self.assertRaises(ValueError): management.save_goal(date.today(),100,{'role':'seller'})
    def test_profit_excludes_stock_purchase_and_preserves_cost(self):
        db.update_product_prices(1,900,1000)
        data=management.monthly_snapshot(date(2026,10,1))
        self.assertEqual(data['profit']['net'],500)
        self.assertEqual(data['profit']['stock_payments'],500)
        self.assertEqual(data['debt_total'],1300)
    def test_products_discount_and_unsold(self):
        top,unsold=management.product_analysis(date(2026,10,1),date(2026,10,31))
        self.assertEqual(top.iloc[0]['Ventes'],1800)
        self.assertEqual(top.iloc[0]['Quantité'],2)
        self.assertEqual(unsold.Produit.tolist(),['Thé'])
        from product_lifecycle import set_archived
        set_archived(self.user,2,True,'Fin de gamme')
        self.assertTrue(management.product_analysis(date(2026,10,1),date(2026,10,31))[1].empty)
    def test_current_debt_includes_other_month(self):
        data=management.monthly_snapshot(date(2026,9,1))
        self.assertEqual(data['profit']['revenue'],0)
        self.assertEqual(data['debt_total'],1300)
    def test_return_reduces_product_ranking(self):
        import v3_db
        v3_db.process_return(self.sale,1,1,'Article retourné','REMBOURSEMENT','Especes',self.user['id'])
        top,_=management.product_analysis(date(2026,10,1),date(2026,10,31))
        self.assertEqual(top.iloc[0]['Quantité'],1)
        self.assertEqual(top.iloc[0]['Ventes'],900)
    def test_product_analysis_with_cloud_records(self):
        expected=management.product_analysis(date(2026,10,1),date(2026,10,31))
        tables={table:features.records(table) for table in ('products','sales','sale_items','store_stock')}
        with patch.object(cloud_db,'enabled',return_value=True),patch.object(features,'records',side_effect=lambda table:tables[table]),patch('product_lifecycle.archived_ids',return_value=set()):
            actual=management.product_analysis(date(2026,10,1),date(2026,10,31))
        import pandas as pd
        for one,two in zip(expected,actual): pd.testing.assert_frame_equal(one,two)
    def test_reminder_current_balance_and_no_sending(self):
        db.add_credit_payment(1,self.sale,300,'Wave',self.user['id'])
        phone,message=management.client_reminder(1,self.user)
        self.assertEqual(phone,'771234567');self.assertIn('1,000 FCFA',message)
        with self.assertRaises(ValueError): management.client_reminder(1,{'role':'seller'})
    def test_monthly_and_client_pdf(self):
        data=management.monthly_snapshot(date(2026,10,1))
        text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(pdf.monthly_pdf(data))).pages)
        for term in ('Bilan mensuel','Bénéfice net estimé','Thé','Transport','1300'):
            self.assertIn(term.replace('1300','1 300'),text)
        profile=workflows.client_profile(1,self.user)
        text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(pdf.client_pdf(profile))).pages)
        self.assertIn('Awa',text);self.assertIn('1 300',text)
    def test_monthly_ui_save_goal_and_downloads(self):
        source='import monthly_management_ui as ui\nui.monthly_page('+repr(self.user)+')'
        app=AppTest.from_string(source,default_timeout=25).run()
        self.assertFalse(app.exception)
        app.date_input[0].set_value(date(2026,10,1)).run()
        app.number_input[0].set_value(5000)
        next(b for b in app.button if b.label=='Enregistrer l’objectif').click().run()
        self.assertFalse(app.exception);self.assertEqual(management.goal(date(2026,10,1)),5000)
        self.assertEqual(len(app.get('download_button')),3)
    def test_client_ui_reminder_confirmation(self):
        source='import monthly_management_ui as ui\nimport workflow_service as service\nuser='+repr(self.user)+'\nui.client_actions(service.client_profile(1,user),user)'
        app=AppTest.from_string(source,default_timeout=25).run()
        self.assertFalse(app.exception);self.assertFalse(app.get('link_button'))
        app.checkbox[0].check().run()
        self.assertFalse(app.exception);self.assertEqual(len(app.get('link_button')),1)
        app.text_area[0].set_value('Nouveau message').run()
        self.assertFalse(app.get('link_button'))
    def test_grouped_reminders_route(self):
        source='import daily_operations_ui as ui\nui.reminders_page('+repr(self.user)+')'
        app=AppTest.from_string(source,default_timeout=25).run()
        self.assertFalse(app.exception)
        app.radio[0].set_value('Par client : tous les impayés').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value,'1 300 FCFA')
        self.assertEqual(len(app.get('download_button')),2)
