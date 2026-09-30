"""Regression tests for inventory reasons and printed barcode labels."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from io import BytesIO

import pandas as pd
from pypdf import PdfReader

import cloud_db
import db
from v4_pdf import make_barcode_labels_pdf


class InventoryBarcodeGuardTests(TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.folder.name) / "test.db"
        with patch.object(cloud_db, "enabled", return_value=False):
            db.init_db()
            db.add_product("Chargeur", "Accessoires", 100, 200, 5, 1, None)
            self.product_id = int(db.products().iloc[0].id)

    def tearDown(self):
        db.DB_PATH = self.old_path
        self.folder.cleanup()

    def test_inventory_difference_requires_reason_and_writes_nothing(self):
        with self.assertRaisesRegex(ValueError, "motif"):
            db.save_inventory_count(self.product_id, 3, 1, "")
        self.assertEqual(int(db.products().iloc[0].Stock), 5)
        self.assertTrue(db.inventory_history().empty)

    def test_inventory_difference_saves_reason(self):
        db.save_inventory_count(self.product_id, 3, 1, "Deux unités manquantes")
        history = db.inventory_history()
        self.assertEqual(int(history.iloc[0].Ecart), -2)
        self.assertEqual(history.iloc[0].Notes, "Deux unités manquantes")

    def test_cloud_inventory_difference_requires_reason_before_stock_change(self):
        table = type("Table", (), {"insert": lambda self, payload: self, "execute": lambda self: None})()
        with patch.object(cloud_db, "_one", return_value={"stock": 5}), \
             patch.object(cloud_db, "set_stock") as set_stock, \
             patch.object(cloud_db, "_table", return_value=table):
            with self.assertRaisesRegex(ValueError, "motif"):
                cloud_db.save_inventory_count(self.product_id, 3, 1, "")
            set_stock.assert_not_called()

    def test_barcode_pdf_omits_products_without_a_registered_barcode(self):
        products = pd.DataFrame([
            {"id": 1, "Produit": "Produit sans code", "Code_barres": "", "Vente": 100},
            {"id": 2, "Produit": "Produit avec code", "Code_barres": "5901234123457", "Vente": 200},
        ])
        pdf = make_barcode_labels_pdf(products, {})
        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
        self.assertIn("5901234123457", text)
        self.assertIn("Produit avec code", text)
        self.assertNotIn("Produit sans code", text)


if __name__ == "__main__":
    import unittest
    unittest.main()
