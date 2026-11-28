# -*- coding: utf-8 -*-
"""Автоматические тесты слоя данных приложения «Флора» (unittest)."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db  # noqa: E402


class FloraDbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        db.init(os.path.join(self.tmp, "test.db"))
        self.user = db.create_user("anna", "pass1234", "Анна", "+79990001122")
        self.when = datetime.now() + timedelta(hours=3)

    def flower(self, name):
        return [f for f in db.list_flowers(name) if f["name"] == name][0]

    def order(self, cart, method="Самовывоз", promo=""):
        return db.place_order(self.user["id"], cart, method, "ул. Тестовая, 1",
                              self.when, "+79990001122", "", promo)

    # --- каталог
    def test_catalog_has_at_least_30_flowers(self):
        self.assertGreaterEqual(len(db.list_flowers()), 30)

    def test_search_is_case_insensitive_for_cyrillic(self):
        self.assertEqual([f["name"] for f in db.list_flowers("ТЮЛЬ")], ["Тюльпан"])

    def test_filter_by_category(self):
        res = db.list_flowers(category="Луковичные")
        self.assertTrue(res and all(f["category"] == "Луковичные" for f in res))

    def test_sort_by_price_desc(self):
        prices = [f["price"] for f in db.list_flowers(sort="price_desc")]
        self.assertEqual(prices, sorted(prices, reverse=True))

    # --- пользователи
    def test_admin_exists_and_can_login(self):
        self.assertEqual(db.authenticate("admin", "admin123")["role"], "admin")

    def test_wrong_password_rejected(self):
        self.assertIsNone(db.authenticate("anna", "wrong"))

    def test_duplicate_login_rejected(self):
        with self.assertRaises(ValueError):
            db.create_user("ANNA", "other1234")

    def test_short_password_rejected(self):
        with self.assertRaises(ValueError):
            db.create_user("petr", "123")

    def test_password_is_not_stored_in_plain_text(self):
        row = db._conn.execute("SELECT pw_hash FROM users WHERE username='anna'").fetchone()
        self.assertNotIn("pass1234", row["pw_hash"])
        self.assertEqual(len(row["pw_hash"]), 64)

    # --- заказы и склад
    def test_order_decreases_stock(self):
        rose = self.flower("Роза")
        self.order({rose["id"]: 5})
        self.assertEqual(db.get_flower(rose["id"])["stock"], rose["stock"] - 5)

    def test_cannot_order_more_than_stock(self):
        rose = self.flower("Роза")
        with self.assertRaises(ValueError):
            self.order({rose["id"]: rose["stock"] + 1})

    def test_cannot_order_out_of_stock_flower(self):
        peony = self.flower("Пион")
        self.assertEqual(peony["stock"], 0)
        with self.assertRaises(ValueError):
            self.order({peony["id"]: 1})

    def test_empty_cart_rejected(self):
        with self.assertRaises(ValueError):
            self.order({})

    def test_promo_discount_and_delivery_fee(self):
        t = db.calc_totals(750, "Доставка", "SPRING10")
        self.assertEqual((t["discount"], t["delivery"], t["total"]), (75, 300, 975))

    def test_free_delivery_from_threshold(self):
        self.assertEqual(db.calc_totals(3000, "Доставка")["delivery"], 0)

    def test_unknown_promo_ignored(self):
        self.assertEqual(db.calc_totals(1000, "Самовывоз", "XXX")["discount"], 0)

    def test_cancel_returns_stock(self):
        rose = self.flower("Роза")
        oid = self.order({rose["id"]: 4})
        db.set_order_status(oid, "Отменён")
        self.assertEqual(db.get_flower(rose["id"])["stock"], rose["stock"])

    def test_closed_order_cannot_change_status(self):
        rose = self.flower("Роза")
        oid = self.order({rose["id"]: 1})
        db.set_order_status(oid, "Отменён")
        with self.assertRaises(ValueError):
            db.set_order_status(oid, "Готов")

    def test_status_flow_and_revenue(self):
        rose = self.flower("Роза")
        oid = self.order({rose["id"]: 2})
        for st in ("В работе", "Готов", "Завершён"):
            db.set_order_status(oid, st)
        s = db.stats()
        self.assertEqual((s["total_orders"], s["active"], s["revenue"]), (1, 0, rose["price"] * 2))

    # --- избранное
    def test_favorites_toggle(self):
        rose = self.flower("Роза")
        self.assertTrue(db.toggle_fav(self.user["id"], rose["id"]))
        self.assertIn(rose["id"], db.fav_ids(self.user["id"]))
        self.assertFalse(db.toggle_fav(self.user["id"], rose["id"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
