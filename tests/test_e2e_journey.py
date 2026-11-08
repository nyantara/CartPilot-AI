import unittest
import sqlite3
import json
from unittest.mock import MagicMock, patch

from app.database.db import init_db, get_db
from app.services.catalogue_service import CatalogueService
from app.services.cart_service import CartService
from app.services.ai_service import AIService
from app.services.order_service import OrderService
from app.services.dashboard_service import DashboardService
from app.schemas.chat import StructuredAIOutput, ExtractedItem

class TestEndToEndUserJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        with get_db() as conn:
            conn.execute("DELETE FROM order_items")
            conn.execute("DELETE FROM orders")
            conn.execute("DELETE FROM cart_items")
            conn.execute("DELETE FROM carts")
            # Reset stock for tested items
            conn.execute("UPDATE products SET stock = 40 WHERE id = 'prod_nb_exec'")
            conn.execute("UPDATE products SET stock = 50 WHERE id = 'prod_pen_gel'")

    def _mock_paypal_client(self, amount: str = "39.97"):
        mock_client = MagicMock()
        mock_client.create_order.return_value = {
            "id": "PAYPAL_E2E_ORDER_777",
            "status": "CREATED"
        }
        mock_client.capture_order.return_value = {
            "id": "PAYPAL_E2E_ORDER_777",
            "status": "COMPLETED",
            "payer": {
                "name": {"given_name": "Hackathon", "surname": "Tester"},
                "email_address": "tester@sandbox.paypal.com"
            },
            "purchase_units": [
                {
                    "payments": {
                        "captures": [
                            {
                                "id": "CAPTURE_E2E_777",
                                "status": "COMPLETED",
                                "amount": {
                                    "value": amount,
                                    "currency_code": "USD"
                                }
                            }
                        ]
                    }
                }
            ]
        }
        return mock_client

    def test_complete_customer_to_checkout_to_merchant_journey(self):
        """
        End-to-End Simulation:
        1. AI processes customer shopping request.
        2. Cart is populated and verified.
        3. PayPal checkout order is created.
        4. Payment is captured and verified.
        5. Stock is deducted and cart is cleared.
        6. Merchant dashboard reflects updated revenue and KPIs.
        7. Idempotency guarantees are preserved.
        """
        session_id = "e2e_session_buyer_01"

        # --- STEP 1: Conversational AI Request ---
        mock_structured_output = StructuredAIOutput(
            intent="add_to_cart",
            budget=50.0,
            items=[
                ExtractedItem(product_query="Executive Hardcover Notebook", quantity=2, variant={"sizes": "A5"}),
                ExtractedItem(product_query="Minimalist Gel Ink Pen Set", quantity=1, variant={"colors": "Blue"})
            ],
            response_message="I've added two Executive Hardcover Notebooks (A5) and one Blue Gel Pen set to your cart for PayPal checkout.",
            suggestions=["View my cart", "Proceed to checkout", "Show pens"]
        )

        with patch.object(AIService, "call_gemini", return_value=mock_structured_output):
            chat_resp = AIService.process_shopping_message(
                session_id=session_id,
                message="I need two A5 notebooks and one blue pen. Budget is $50."
            )

        self.assertEqual(chat_resp.intent, "add_to_cart")
        self.assertEqual(len(chat_resp.items), 2)
        self.assertEqual(chat_resp.items[0].status, "available")
        self.assertEqual(chat_resp.items[1].status, "available")

        # --- STEP 2: Verify Persistent SQLite Cart ---
        cart = CartService.get_cart(session_id)
        self.assertIsNotNone(cart)
        self.assertEqual(len(cart["items"]), 2)
        # 2 * 14.99 ($29.98) + 1 * 9.99 ($9.99) = $39.97
        self.assertEqual(cart["subtotal"], 39.97)

        # Ensure stock is NOT deducted yet
        prod_nb = CatalogueService.get_product_by_id("prod_nb_exec")
        prod_pen = CatalogueService.get_product_by_id("prod_pen_gel")
        self.assertEqual(prod_nb["stock"], 40)
        self.assertEqual(prod_pen["stock"], 50)

        # --- STEP 3: Create PayPal Checkout Order ---
        mock_paypal = self._mock_paypal_client(amount="39.97")
        order_info = OrderService.create_order_from_cart(
            session_id=session_id,
            customer_name="Hackathon Tester",
            customer_email="tester@sandbox.paypal.com",
            paypal_client_override=mock_paypal
        )

        self.assertIsNotNone(order_info["order_id"])
        self.assertEqual(order_info["paypal_order_id"], "PAYPAL_E2E_ORDER_777")
        self.assertEqual(order_info["total_amount"], 39.97)
        self.assertEqual(order_info["status"], "PENDING")

        # Stock must STILL remain intact
        prod_nb = CatalogueService.get_product_by_id("prod_nb_exec")
        self.assertEqual(prod_nb["stock"], 40)

        # Merchant dashboard before capture: total_sales = 0.0, pending = 1
        dash_pre = DashboardService.get_dashboard_summary()
        self.assertEqual(dash_pre["total_sales"], 0.0)
        self.assertEqual(dash_pre["pending_payments"], 1)

        # --- STEP 4: PayPal Payment Capture ---
        capture_result = OrderService.capture_and_finalize_order(
            order_identifier=order_info["order_id"],
            session_id=session_id,
            paypal_client_override=mock_paypal
        )

        self.assertEqual(capture_result["status"], "COMPLETED")
        self.assertEqual(capture_result["amount_captured"], 39.97)
        self.assertEqual(capture_result["capture_id"], "CAPTURE_E2E_777")

        # --- STEP 5: Verify SQLite State (Stock Decremented & Cart Cleared) ---
        prod_nb_after = CatalogueService.get_product_by_id("prod_nb_exec")
        prod_pen_after = CatalogueService.get_product_by_id("prod_pen_gel")
        self.assertEqual(prod_nb_after["stock"], 38) # 40 - 2
        self.assertEqual(prod_pen_after["stock"], 49) # 50 - 1

        cart_after = CartService.get_cart(session_id)
        self.assertEqual(len(cart_after["items"]), 0)
        self.assertEqual(cart_after["subtotal"], 0.0)

        # --- STEP 6: Merchant Dashboard Verification ---
        dash_post = DashboardService.get_dashboard_summary()
        self.assertEqual(dash_post["total_orders"], 1)
        self.assertEqual(dash_post["successful_payments"], 1)
        self.assertEqual(dash_post["pending_payments"], 0)
        self.assertEqual(dash_post["total_sales"], 39.97)
        self.assertEqual(len(dash_post["recent_orders"]), 1)
        self.assertEqual(dash_post["recent_orders"][0]["payment_status"], "COMPLETED")

        # --- STEP 7: Idempotency Protection ---
        # Calling capture again on the same order returns existing completed record without deducting stock again
        idempotent_result = OrderService.capture_and_finalize_order(
            order_identifier=order_info["order_id"],
            session_id=session_id,
            paypal_client_override=mock_paypal
        )
        self.assertEqual(idempotent_result["status"], "COMPLETED")
        prod_nb_idempotent = CatalogueService.get_product_by_id("prod_nb_exec")
        self.assertEqual(prod_nb_idempotent["stock"], 38) # Stock not decremented twice!

if __name__ == "__main__":
    unittest.main()
