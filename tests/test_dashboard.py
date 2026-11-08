import unittest
import sqlite3
import json

from app.database.db import init_db, get_db
from app.services.dashboard_service import DashboardService
from app.routes.dashboard import get_dashboard_summary

class TestDashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        with get_db() as conn:
            conn.execute("DELETE FROM order_items")
            conn.execute("DELETE FROM orders")
            conn.execute("DELETE FROM cart_items")
            conn.execute("DELETE FROM carts")
            # Reset stock for products
            conn.execute("UPDATE products SET stock = 40 WHERE id = 'prod_nb_exec'")
            conn.execute("UPDATE products SET stock = 12 WHERE id = 'prod_bk_pragmatic'")  # low stock <= 20

    def test_01_empty_dashboard_summary(self):
        """Scenario 1: With no orders, metrics show zeroes and zero revenue."""
        summary = DashboardService.get_dashboard_summary()
        self.assertEqual(summary["total_orders"], 0)
        self.assertEqual(summary["successful_payments"], 0)
        self.assertEqual(summary["pending_payments"], 0)
        self.assertEqual(summary["failed_payments"], 0)
        self.assertEqual(summary["cancelled_payments"], 0)
        self.assertEqual(summary["total_sales"], 0.0)
        self.assertEqual(summary["currency"], "USD")
        self.assertEqual(len(summary["recent_orders"]), 0)
        self.assertGreater(summary["total_products"], 0)

    def test_02_order_status_counts_and_revenue(self):
        """Scenario 2: Total sales only counts COMPLETED orders, metrics properly categorized."""
        with get_db() as conn:
            # 1 COMPLETED order ($50.00)
            conn.execute("""
                INSERT INTO orders (id, session_id, customer_name, customer_email, total_amount, currency, payment_status, paypal_order_id, paypal_capture_id)
                VALUES ('ord_comp_1', 'sess_1', 'John Doe', 'john@example.com', 50.00, 'USD', 'COMPLETED', 'PAY_1', 'CAP_1')
            """)
            # 1 PENDING order ($25.00)
            conn.execute("""
                INSERT INTO orders (id, session_id, customer_name, customer_email, total_amount, currency, payment_status, paypal_order_id)
                VALUES ('ord_pend_1', 'sess_2', 'Jane Doe', 'jane@example.com', 25.00, 'USD', 'PENDING', 'PAY_2')
            """)
            # 1 CANCELLED order ($15.00)
            conn.execute("""
                INSERT INTO orders (id, session_id, customer_name, customer_email, total_amount, currency, payment_status, paypal_order_id)
                VALUES ('ord_canc_1', 'sess_3', 'Bob Smith', 'bob@example.com', 15.00, 'USD', 'CANCELLED', 'PAY_3')
            """)
            # 1 FAILED order ($10.00)
            conn.execute("""
                INSERT INTO orders (id, session_id, customer_name, customer_email, total_amount, currency, payment_status, paypal_order_id)
                VALUES ('ord_fail_1', 'sess_4', 'Alice Green', 'alice@example.com', 10.00, 'USD', 'FAILED', 'PAY_4')
            """)

        summary = DashboardService.get_dashboard_summary()
        self.assertEqual(summary["total_orders"], 4)
        self.assertEqual(summary["successful_payments"], 1)
        self.assertEqual(summary["pending_payments"], 1)
        self.assertEqual(summary["cancelled_payments"], 1)
        self.assertEqual(summary["failed_payments"], 1)
        self.assertEqual(summary["total_sales"], 50.00)

    def test_03_low_stock_alerts(self):
        """Scenario 3: Products with stock <= 20 trigger low stock alerts sorted ascending."""
        summary = DashboardService.get_dashboard_summary()
        alerts = summary["low_stock_alerts"]
        self.assertTrue(any(p["id"] == "prod_bk_pragmatic" for p in alerts))
        prag_alert = next(p for p in alerts if p["id"] == "prod_bk_pragmatic")
        self.assertEqual(prag_alert["stock"], 12)

    def test_04_recent_orders_items_retrieval(self):
        """Scenario 4: Recent orders include full line item breakdown."""
        with get_db() as conn:
            conn.execute("""
                INSERT INTO orders (id, session_id, customer_name, customer_email, total_amount, currency, payment_status, paypal_order_id)
                VALUES ('ord_with_items', 'sess_items', 'Charlie Brown', 'charlie@example.com', 30.00, 'USD', 'COMPLETED', 'PAY_5')
            """)
            conn.execute("""
                INSERT INTO order_items (order_id, product_id, product_name, quantity, unit_price, subtotal, variant_details)
                VALUES ('ord_with_items', 'prod_nb_exec', 'Executive Hardcover Notebook', 2, 15.00, 30.00, '{"sizes":"A5"}')
            """)

        summary = DashboardService.get_dashboard_summary()
        self.assertEqual(len(summary["recent_orders"]), 1)
        recent = summary["recent_orders"][0]
        self.assertEqual(recent["id"], "ord_with_items")
        self.assertEqual(len(recent["items"]), 1)
        self.assertEqual(recent["items"][0]["product_id"], "prod_nb_exec")
        self.assertEqual(recent["items"][0]["quantity"], 2)

    def test_05_dashboard_api_endpoint(self):
        """Scenario 5: Calling the endpoint function returns valid DashboardSummaryResponse."""
        response = get_dashboard_summary()
        self.assertEqual(response.currency, "USD")
        self.assertIsInstance(response.total_orders, int)
        self.assertIsInstance(response.total_sales, float)
        self.assertIsInstance(response.low_stock_alerts, list)

if __name__ == "__main__":
    unittest.main()
