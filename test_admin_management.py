"""Administrative deletion rules on an isolated SQLite database."""
from pathlib import Path
from tempfile import TemporaryDirectory

import db


def rejects(action):
    try:
        action()
    except ValueError:
        return
    raise AssertionError("Une opération liée à un historique a été acceptée.")


def run():
    with TemporaryDirectory() as folder:
        db.DB_PATH = Path(folder) / "admin.db"
        db.init_db()
        db.add_client("Client libre", "", "", "")
        db.add_client("Client lié", "", "", "")
        db.add_supplier("Fournisseur libre", "", "", "", "")
        db.add_supplier("Fournisseur lié", "", "", "", "")
        db.add_product("Riz", "Épicerie", 500, 1000, 10, 1, 2)
        rejects(lambda: db.delete_supplier(2))
        db.delete_supplier(1)
        assert list(db.suppliers().Fournisseur) == ["Fournisseur lié"]
        paid_sale = db.save_sale([{"id": 1, "quantity": 1, "sale_price": 1000}], 1, 2, 1000, "Especes", 0)[0]
        rejects(lambda: db.delete_client(2))
        rejects(lambda: db.delete_sale(paid_sale))
        rejects(lambda: db.update_sale(paid_sale, 2, 1200, "Especes", 0))
        assert int(db.products().iloc[0].Stock) == 9
        unpaid_sale = db.save_sale([{"id": 1, "quantity": 1, "sale_price": 1000}], 1, 2, 0, "Credit", 0)[0]
        db.delete_sale(unpaid_sale)
        assert db.sale_details(unpaid_sale) is None
        assert int(db.products().iloc[0].Stock) == 9
        db.delete_client(1)
        assert list(db.clients().Client) == ["Client lié"]
        rejects(lambda: db.delete_client(2))
    print("PASS: unlinked client/supplier deletion, historical guards, paid-sale protection and unpaid stock restoration")


if __name__ == "__main__":
    run()
