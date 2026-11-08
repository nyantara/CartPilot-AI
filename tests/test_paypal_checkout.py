import unittest
import sqlite3
import json
from unittest.mock import MagicMock, patch

from app.database.db import init_db, get_db
from app.config import settings
from app.services.catalogue_service import CatalogueService
from app.services.cart_service import CartService
from app.services.order_service import OrderService
from app.services.paypal_service import PayPalService, PayPalAPIError, PayPalConfigError

class TestPayPalCheckout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        # Reset cart and order tables before each test
        with get_db() as conn:
            conn.execute("DELETE FROM order_items")
            conn.execute("DELETE FROM orders")
            conn.execute("DELETE FROM cart_items")
            conn.execute("DELETE FROM carts")
            # Ensure notebook has stock reset to 40
            conn.execute("UPDATE products SET stock = 40 WHERE id = 'prod_nb_exec'")

    def _create_mock_paypal_client(self, amount="29.98", currency="USD", capture_status="COMPLETED", capture_id="CAP_123456"):
        """Helper to create a mock PayPalService client."""
        mock_client = MagicMock()
        mock_client.create_order.return_value = {
            "id": "PAYPAL_ORD_TEST_999",
            "status": "CREATED"
        }
        mock_client.capture_order.return_value = {
            "id": "PAYPAL_ORD_TEST_999",
            "status": capture_status,
            "payer": {
                "name": {"given_name": "Test", "surname": "Buyer"},
                "email_address": "test.buyer@sandbox.paypal.com"
            },
            "purchase_units": [
                {
                    "payments": {
                        "captures": [
                            {
                                "id": capture_id,
                                "status": capture_status,
                                "amount": {
                                    "value": str(amount),
                                    "currency_code": str(currency)
                                }
                            }
                        ]
                    }
                }
            ]
        }
        return mock_client

    def test_01_empty_cart_checkout_rejection(self):
        """Scenario 1: Checkout with an empty cart is rejected with ValueError."""
        with self.assertRaises(ValueError) as ctx:
            OrderService.create_order_from_cart(session_id="empty-sess")
        self.assertIn("empty", str(ctx.exception).lower())

    def test_02_valid_order_creation(self):
        """Scenario 2: Creating a valid checkout order from cart items."""
        session_id = "sess-create-order"
        CartService.add_item(session_id, "prod_nb_exec", quantity=2, selected_variants={"sizes": "A5"})
        
        mock_paypal = self._create_mock_paypal_client(amount="29.98")
        order_info = OrderService.create_order_from_cart(
            session_id=session_id,
            customer_name="Alice Smith",
            customer_email="alice@example.com",
            paypal_client_override=mock_paypal
        )

        self.assertIsNotNone(order_info["order_id"])
        self.assertEqual(order_info["paypal_order_id"], "PAYPAL_ORD_TEST_999")
        self.assertEqual(order_info["total_amount"], 29.98)
        self.assertEqual(order_info["status"], "PENDING")

        # Verify draft order persisted in SQLite
        order_db = OrderService.get_order(order_info["order_id"])
        self.assertIsNotNone(order_db)
        self.assertEqual(order_db["payment_status"], "PENDING")
        self.assertEqual(len(order_db["items"]), 1)
        self.assertEqual(order_db["items"][0]["quantity"], 2)

    def test_03_price_manipulation_rejection(self):
        """Scenario 3: Client cannot manipulate prices; prices are strictly sourced from SQLite."""
        session_id = "sess-price-test"
        # Executive Hardcover Notebook is $14.99 in DB
        CartService.add_item(session_id, "prod_nb_exec", quantity=2, selected_variants={"sizes": "A5"})
        
        mock_paypal = self._create_mock_paypal_client(amount="29.98")
        order_info = OrderService.create_order_from_cart(session_id=session_id, paypal_client_override=mock_paypal)
        
        # 2 * 14.99 = 29.98 strictly
        self.assertEqual(order_info["total_amount"], 29.98)

    def test_04_stock_changes_before_checkout(self):
        """Scenario 4: Rechecking stock rejects checkout if inventory depleted before checkout."""
        session_id = "sess-stock-depleted"
        CartService.add_item(session_id, "prod_nb_exec", quantity=5, selected_variants={"sizes": "A5"})

        # Deplete stock in database externally before user creates order
        with get_db() as conn:
            conn.execute("UPDATE products SET stock = 2 WHERE id = 'prod_nb_exec'")

        mock_paypal = self._create_mock_paypal_client()
        with self.assertRaises(ValueError) as ctx:
            OrderService.create_order_from_cart(session_id=session_id, paypal_client_override=mock_paypal)
        self.assertIn("Insufficient stock", str(ctx.exception))

    def test_05_paypal_api_failure(self):
        """Scenario 5: PayPal API network failure raises PayPalAPIError."""
        session_id = "sess-paypal-fail"
        CartService.add_item(session_id, "prod_nb_exec", quantity=1, selected_variants={"sizes": "A5"})

        mock_paypal = MagicMock()
        mock_paypal.create_order.side_effect = PayPalAPIError("Simulated PayPal Gateway Error", status_code=502)

        with self.assertRaises(PayPalAPIError) as ctx:
            OrderService.create_order_from_cart(session_id=session_id, paypal_client_override=mock_paypal)
        self.assertEqual(ctx.exception.status_code, 502)

    def test_06_successful_payment_capture(self):
        """Scenario 6: Successful payment capture finalizes order and empties cart."""
        session_id = "sess-capture-success"
        CartService.add_item(session_id, "prod_nb_exec", quantity=2, selected_variants={"sizes": "A5"})
        
        mock_paypal = self._create_mock_paypal_client(amount="29.98", capture_id="CAPTURE_SUCCESS_111")
        order_info = OrderService.create_order_from_cart(session_id=session_id, paypal_client_override=mock_paypal)

        capture_res = OrderService.capture_and_finalize_order(
            order_identifier=order_info["order_id"],
            session_id=session_id,
            paypal_client_override=mock_paypal
        )

        self.assertEqual(capture_res["status"], "COMPLETED")
        self.assertEqual(capture_res["capture_id"], "CAPTURE_SUCCESS_111")
        self.assertEqual(capture_res["amount_captured"], 29.98)

        # Cart should now be empty
        cleared_cart = CartService.get_cart(session_id)
        self.assertEqual(len(cleared_cart["items"]), 0)

        # Order status in DB is COMPLETED
        db_order = OrderService.get_order(order_info["order_id"])
        self.assertEqual(db_order["payment_status"], "COMPLETED")
        self.assertEqual(db_order["paypal_capture_id"], "CAPTURE_SUCCESS_111")

    def test_07_failed_payment_capture(self):
        """Scenario 7: Failed PayPal capture updates order to FAILED without clearing cart or deducting stock."""
        session_id = "sess-capture-fail"
        CartService.add_item(session_id, "prod_nb_exec", quantity=2, selected_variants={"sizes": "A5"})
        
        mock_paypal = self._create_mock_paypal_client(capture_status="DENIED")
        order_info = OrderService.create_order_from_cart(session_id=session_id, paypal_client_override=mock_paypal)

        with self.assertRaises(ValueError) as ctx:
            OrderService.capture_and_finalize_order(
                order_identifier=order_info["order_id"],
                session_id=session_id,
                paypal_client_override=mock_paypal
            )
        self.assertIn("not completed", str(ctx.exception))

        # Order status must be FAILED
        db_order = OrderService.get_order(order_info["order_id"])
        self.assertEqual(db_order["payment_status"], "FAILED")

        # Cart must still contain items
        cart = CartService.get_cart(session_id)
        self.assertEqual(len(cart["items"]), 1)

        # Stock must NOT be deducted
        prod = CatalogueService.get_product_by_id("prod_nb_exec")
        self.assertEqual(prod["stock"], 40)

    def test_08_cancelled_payment(self):
        """Scenario 8: Cancelled checkout marks order CANCELLED and preserves cart."""
        session_id = "sess-cancel"
        CartService.add_item(session_id, "prod_nb_exec", quantity=1, selected_variants={"sizes": "A5"})
        mock_paypal = self._create_mock_paypal_client(amount="14.99")
        order_info = OrderService.create_order_from_cart(session_id=session_id, paypal_client_override=mock_paypal)

        cancel_res = OrderService.cancel_order(order_info["order_id"])
        self.assertEqual(cancel_res["status"], "CANCELLED")

        db_order = OrderService.get_order(order_info["order_id"])
        self.assertEqual(db_order["payment_status"], "CANCELLED")

        # Cart is preserved
        cart = CartService.get_cart(session_id)
        self.assertEqual(len(cart["items"]), 1)

    def test_09_duplicate_capture_request_idempotency(self):
        """Scenario 9: Repeated capture calls for an already completed order return completed status safely."""
        session_id = "sess-idempotent"
        CartService.add_item(session_id, "prod_nb_exec", quantity=1, selected_variants={"sizes": "A5"})
        mock_paypal = self._create_mock_paypal_client(amount="14.99", capture_id="CAP_IDEM_1")
        order_info = OrderService.create_order_from_cart(session_id=session_id, paypal_client_override=mock_paypal)

        # First capture
        res1 = OrderService.capture_and_finalize_order(order_info["order_id"], paypal_client_override=mock_paypal)
        self.assertEqual(res1["status"], "COMPLETED")

        # Second capture (e.g. repeated click or network retry)
        res2 = OrderService.capture_and_finalize_order(order_info["order_id"], paypal_client_override=mock_paypal)
        self.assertEqual(res2["status"], "COMPLETED")
        self.assertIn("already successfully captured", res2["message"])

    def test_10_incorrect_capture_amount_fraud_protection(self):
        """Scenario 10: Amount mismatch between expected order total and captured amount triggers fraud error."""
        session_id = "sess-amount-mismatch"
        CartService.add_item(session_id, "prod_nb_exec", quantity=2, selected_variants={"sizes": "A5"})
        # Expected is $29.98, but PayPal returns $5.00
        mock_paypal = self._create_mock_paypal_client(amount="5.00")
        order_info = OrderService.create_order_from_cart(session_id=session_id, paypal_client_override=mock_paypal)

        with self.assertRaises(ValueError) as ctx:
            OrderService.capture_and_finalize_order(order_info["order_id"], paypal_client_override=mock_paypal)
        self.assertIn("Amount mismatch", str(ctx.exception))

        # Order must be marked FAILED
        db_order = OrderService.get_order(order_info["order_id"])
        self.assertEqual(db_order["payment_status"], "FAILED")

    def test_11_incorrect_currency_protection(self):
        """Scenario 11: Currency mismatch between order and capture is rejected."""
        session_id = "sess-curr-mismatch"
        CartService.add_item(session_id, "prod_nb_exec", quantity=2, selected_variants={"sizes": "A5"})
        # Expected USD, PayPal returns EUR
        mock_paypal = self._create_mock_paypal_client(amount="29.98", currency="EUR")
        order_info = OrderService.create_order_from_cart(session_id=session_id, paypal_client_override=mock_paypal)

        with self.assertRaises(ValueError) as ctx:
            OrderService.capture_and_finalize_order(order_info["order_id"], paypal_client_override=mock_paypal)
        self.assertIn("Currency mismatch", str(ctx.exception))

    def test_12_duplicate_stock_deduction_prevention(self):
        """Scenario 12: Idempotent captures never deduct stock multiple times."""
        session_id = "sess-stock-dedup"
        # Initial stock is 40
        CartService.add_item(session_id, "prod_nb_exec", quantity=2, selected_variants={"sizes": "A5"})
        mock_paypal = self._create_mock_paypal_client(amount="29.98")
        order_info = OrderService.create_order_from_cart(session_id=session_id, paypal_client_override=mock_paypal)

        # First capture decrements stock: 40 - 2 = 38
        OrderService.capture_and_finalize_order(order_info["order_id"], paypal_client_override=mock_paypal)
        prod_after_cap1 = CatalogueService.get_product_by_id("prod_nb_exec")
        self.assertEqual(prod_after_cap1["stock"], 38)

        # Second capture must NOT decrement stock again!
        OrderService.capture_and_finalize_order(order_info["order_id"], paypal_client_override=mock_paypal)
        prod_after_cap2 = CatalogueService.get_product_by_id("prod_nb_exec")
        self.assertEqual(prod_after_cap2["stock"], 38)

    def test_13_inventory_deduction_after_successful_capture_only(self):
        """Scenario 13: Stock is NOT deducted upon order creation; only upon successful capture."""
        session_id = "sess-stock-timing"
        CartService.add_item(session_id, "prod_nb_exec", quantity=3, selected_variants={"sizes": "A5"})
        mock_paypal = self._create_mock_paypal_client(amount="44.97")

        # Step 1: Create Order
        order_info = OrderService.create_order_from_cart(session_id=session_id, paypal_client_override=mock_paypal)
        prod_mid = CatalogueService.get_product_by_id("prod_nb_exec")
        self.assertEqual(prod_mid["stock"], 40, "Stock must remain unchanged after draft order creation")

        # Step 2: Capture Order
        OrderService.capture_and_finalize_order(order_info["order_id"], paypal_client_override=mock_paypal)
        prod_post = CatalogueService.get_product_by_id("prod_nb_exec")
        self.assertEqual(prod_post["stock"], 37, "Stock must be decremented by 3 after capture")

    def test_14_order_persistence(self):
        """Scenario 14: Completed orders and line items persist cleanly in SQLite."""
        session_id = "sess-persist-order"
        CartService.add_item(session_id, "prod_nb_exec", quantity=1, selected_variants={"sizes": "A5"})
        mock_paypal = self._create_mock_paypal_client(amount="14.99", capture_id="CAP_PERSIST_99")
        order_info = OrderService.create_order_from_cart(session_id=session_id, paypal_client_override=mock_paypal)
        OrderService.capture_and_finalize_order(order_info["order_id"], paypal_client_override=mock_paypal)

        # Read directly using fresh raw SQLite connection
        conn = sqlite3.connect(settings.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE id = ?", (order_info["order_id"],))
        order_row = cur.fetchone()
        cur.execute("SELECT * FROM order_items WHERE order_id = ?", (order_info["order_id"],))
        items_rows = cur.fetchall()
        conn.close()

        self.assertIsNotNone(order_row)
        self.assertEqual(order_row["payment_status"], "COMPLETED")
        self.assertEqual(order_row["paypal_capture_id"], "CAP_PERSIST_99")
        self.assertEqual(len(items_rows), 1)
        self.assertEqual(items_rows[0]["product_id"], "prod_nb_exec")

    def test_15_session_order_isolation(self):
        """Scenario 15: Orders cannot be captured across mismatched sessions."""
        session_a = "sess-user-A"
        session_b = "sess-user-B"

        CartService.add_item(session_a, "prod_nb_exec", quantity=1, selected_variants={"sizes": "A5"})
        mock_paypal = self._create_mock_paypal_client(amount="14.99")
        order_info = OrderService.create_order_from_cart(session_id=session_a, paypal_client_override=mock_paypal)

        # Attempt to capture Session A's order using Session B identifier
        with self.assertRaises(KeyError) as ctx:
            OrderService.capture_and_finalize_order(
                order_identifier=order_info["order_id"],
                session_id=session_b,
                paypal_client_override=mock_paypal
            )
        self.assertIn("does not belong to session", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()

