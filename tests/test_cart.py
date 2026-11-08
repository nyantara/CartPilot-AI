import unittest
import sqlite3
import json
from unittest.mock import MagicMock, patch

from app.database.db import init_db, get_db
from app.config import settings
from app.services.cart_service import CartService
from app.services.ai_service import AIService
from app.schemas.chat import StructuredAIOutput, ExtractedItem

class TestCartManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        # Clear test cart tables before each test
        with get_db() as conn:
            conn.execute("DELETE FROM cart_items")
            conn.execute("DELETE FROM carts")

    def test_01_create_new_cart(self):
        """Scenario 1: Creating a new cart for a session."""
        cart = CartService.get_or_create_cart("session-01")
        self.assertIsNotNone(cart["id"])
        self.assertEqual(cart["session_id"], "session-01")
        self.assertEqual(cart["status"], "ACTIVE")

    def test_02_retrieve_empty_cart(self):
        """Scenario 2: Retrieving an empty cart returns zero items and zero total."""
        cart = CartService.get_cart("session-02")
        self.assertEqual(cart["session_id"], "session-02")
        self.assertEqual(len(cart["items"]), 0)
        self.assertEqual(cart["total_items"], 0)
        self.assertEqual(cart["subtotal"], 0.0)

    def test_03_add_one_product(self):
        """Scenario 3: Adding one valid product to the cart."""
        cart = CartService.add_item(
            session_id="session-03",
            product_id="prod_nb_exec",
            quantity=1,
            selected_variants={"sizes": "A5"}
        )
        self.assertEqual(len(cart["items"]), 1)
        item = cart["items"][0]
        self.assertEqual(item["product_id"], "prod_nb_exec")
        self.assertEqual(item["product_name"], "Executive Hardcover Notebook")
        self.assertEqual(item["quantity"], 1)
        self.assertEqual(item["unit_price"], 14.99)
        self.assertEqual(item["subtotal"], 14.99)
        self.assertEqual(item["selected_variants"].get("sizes"), "A5")
        self.assertEqual(cart["subtotal"], 14.99)
        self.assertEqual(cart["total_items"], 1)

    def test_04_add_multiple_products(self):
        """Scenario 4: Adding distinct products calculates correct cumulative total."""
        CartService.add_item("session-04", "prod_nb_exec", quantity=1, selected_variants={"sizes": "A5"})
        cart = CartService.add_item("session-04", "prod_pen_gel", quantity=2, selected_variants={"colors": "Blue"})

        self.assertEqual(len(cart["items"]), 2)
        self.assertEqual(cart["total_items"], 3)
        # 14.99 + (2 * 9.99) = 14.99 + 19.98 = 34.97
        self.assertEqual(cart["subtotal"], 34.97)

    def test_05_increase_existing_item_quantity(self):
        """Scenario 5: Adding the exact same product and variant increments quantity rather than creating duplicate."""
        CartService.add_item("session-05", "prod_nb_exec", quantity=1, selected_variants={"sizes": "A5"})
        cart = CartService.add_item("session-05", "prod_nb_exec", quantity=2, selected_variants={"sizes": "A5"})

        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["items"][0]["quantity"], 3)
        self.assertEqual(cart["items"][0]["subtotal"], 44.97)
        self.assertEqual(cart["total_items"], 3)
        self.assertEqual(cart["subtotal"], 44.97)

    def test_06_add_same_product_different_variants(self):
        """Scenario 6: Adding same product with different variants creates separate cart items."""
        CartService.add_item("session-06", "prod_nb_exec", quantity=1, selected_variants={"sizes": "A4"})
        cart = CartService.add_item("session-06", "prod_nb_exec", quantity=1, selected_variants={"sizes": "A5"})

        self.assertEqual(len(cart["items"]), 2)
        self.assertEqual(cart["total_items"], 2)
        sizes = [i["selected_variants"].get("sizes") for i in cart["items"]]
        self.assertIn("A4", sizes)
        self.assertIn("A5", sizes)

    def test_07_update_quantity(self):
        """Scenario 7: Updating item quantity recalculates subtotals."""
        cart = CartService.add_item("session-07", "prod_nb_exec", quantity=1, selected_variants={"sizes": "A5"})
        item_id = cart["items"][0]["id"]

        updated_cart = CartService.update_item("session-07", item_id, quantity=4)
        self.assertEqual(updated_cart["items"][0]["quantity"], 4)
        self.assertEqual(updated_cart["items"][0]["subtotal"], 59.96)
        self.assertEqual(updated_cart["subtotal"], 59.96)

    def test_08_update_variants(self):
        """Scenario 8: Updating variant choices for an existing item."""
        cart = CartService.add_item("session-08", "prod_nb_exec", quantity=1, selected_variants={"sizes": "A5"})
        item_id = cart["items"][0]["id"]

        updated_cart = CartService.update_item("session-08", item_id, selected_variants={"sizes": "A4"})
        self.assertEqual(updated_cart["items"][0]["selected_variants"].get("sizes"), "A4")

    def test_09_remove_item(self):
        """Scenario 9: Removing an item updates cart items and subtotals."""
        CartService.add_item("session-09", "prod_nb_exec", quantity=1, selected_variants={"sizes": "A5"})
        cart = CartService.add_item("session-09", "prod_pen_gel", quantity=1, selected_variants={"colors": "Blue"})
        item_id_to_remove = cart["items"][0]["id"]

        updated_cart = CartService.remove_item("session-09", item_id_to_remove)
        self.assertEqual(len(updated_cart["items"]), 1)
        self.assertEqual(updated_cart["items"][0]["product_id"], "prod_pen_gel")
        self.assertEqual(updated_cart["subtotal"], 9.99)

    def test_10_clear_cart(self):
        """Scenario 10: Clearing the cart removes all items."""
        CartService.add_item("session-10", "prod_nb_exec", quantity=1, selected_variants={"sizes": "A5"})
        CartService.add_item("session-10", "prod_pen_gel", quantity=2, selected_variants={"colors": "Black"})

        cleared_cart = CartService.clear_cart("session-10")
        self.assertEqual(len(cleared_cart["items"]), 0)
        self.assertEqual(cleared_cart["total_items"], 0)
        self.assertEqual(cleared_cart["subtotal"], 0.0)

    def test_11_reject_nonexistent_product(self):
        """Scenario 11: Reject adding nonexistent product with KeyError."""
        with self.assertRaises(KeyError) as ctx:
            CartService.add_item("session-11", "non_existent_sku_999", quantity=1)
        self.assertIn("not found in the catalogue", str(ctx.exception))

    def test_12_reject_invalid_variants(self):
        """Scenario 12: Reject invalid variant option."""
        with self.assertRaises(ValueError) as ctx:
            CartService.add_item("session-12", "prod_nb_exec", quantity=1, selected_variants={"sizes": "A1_Gigantic"})
        self.assertIn("not valid for sizes", str(ctx.exception))

    def test_13_reject_insufficient_stock(self):
        """Scenario 13: Reject quantity exceeding available inventory."""
        with self.assertRaises(ValueError) as ctx:
            # Stand has stock = 20
            CartService.add_item("session-13", "prod_acc_stand", quantity=50)
        self.assertIn("Insufficient stock", str(ctx.exception))

    def test_14_reject_invalid_quantities(self):
        """Scenario 14: Reject zero or negative quantities."""
        with self.assertRaises(ValueError):
            CartService.add_item("session-14", "prod_nb_exec", quantity=0)
        with self.assertRaises(ValueError):
            CartService.add_item("session-14", "prod_nb_exec", quantity=-5)

    def test_15_recalculate_totals_correctly(self):
        """Scenario 15: Exact 2-decimal precision calculation without floating point drift."""
        # 3 notebooks (3 * 14.99 = 44.97) + 2 pens (2 * 9.99 = 19.98) = 64.95
        CartService.add_item("session-15", "prod_nb_exec", quantity=3, selected_variants={"sizes": "A5"})
        cart = CartService.add_item("session-15", "prod_pen_gel", quantity=2, selected_variants={"colors": "Black"})
        self.assertEqual(cart["subtotal"], 64.95)

    def test_16_prices_cannot_be_manipulated_by_client(self):
        """Scenario 16: Prices are strictly loaded from SQLite products table."""
        # Attempt to pass product ID without any ability for client to specify price
        cart = CartService.add_item("session-16", "prod_nb_exec", quantity=2, selected_variants={"sizes": "A5"})
        self.assertEqual(cart["items"][0]["unit_price"], 14.99)
        self.assertEqual(cart["items"][0]["subtotal"], 29.98)

    def test_17_persists_across_server_restarts(self):
        """Scenario 17: Carts persist cleanly in SQLite database file."""
        CartService.add_item("session-persist", "prod_nb_exec", quantity=2, selected_variants={"sizes": "A5"})
        
        # Verify directly through independent raw SQLite connection
        conn = sqlite3.connect(settings.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT ci.quantity, ci.unit_price, ci.subtotal, c.session_id
            FROM cart_items ci JOIN carts c ON ci.cart_id = c.id
            WHERE c.session_id = 'session-persist'
        """)
        row = cur.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["quantity"], 2)
        self.assertEqual(row["unit_price"], 14.99)
        self.assertEqual(row["subtotal"], 29.98)

    def test_18_isolate_carts_between_sessions(self):
        """Scenario 18: Isolation between session A and session B."""
        CartService.add_item("session-A", "prod_nb_exec", quantity=1, selected_variants={"sizes": "A5"})
        CartService.add_item("session-B", "prod_pen_gel", quantity=3, selected_variants={"colors": "Blue"})

        cart_a = CartService.get_cart("session-A")
        cart_b = CartService.get_cart("session-B")

        self.assertEqual(len(cart_a["items"]), 1)
        self.assertEqual(cart_a["items"][0]["product_id"], "prod_nb_exec")
        self.assertEqual(cart_a["subtotal"], 14.99)

        self.assertEqual(len(cart_b["items"]), 1)
        self.assertEqual(cart_b["items"][0]["product_id"], "prod_pen_gel")
        self.assertEqual(cart_b["subtotal"], 29.97)

    def test_19_integrate_ai_add_to_cart_with_persistent_cart(self):
        """Scenario 19: AI add-to-cart request automatically populates the persistent cart."""
        mock_output = StructuredAIOutput(
            intent="add_to_cart",
            items=[ExtractedItem(product_query="Executive Hardcover Notebook", quantity=2, variant={"sizes": "A5"})],
            response_message="I've added two A5 notebooks to your cart."
        )
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = mock_output.model_dump_json()
        mock_client.models.generate_content.return_value = mock_resp

        # Process through AI shopping assistant
        chat_resp = AIService.process_shopping_message(
            message="Add two A5 notebooks to my cart",
            session_id="ai-cart-session",
            client_override=mock_client
        )

        self.assertIsNotNone(chat_resp.cart)
        self.assertEqual(chat_resp.cart.total_items, 2)
        self.assertEqual(chat_resp.cart.subtotal, 29.98)

        # Confirm persisted in SQLite
        persisted_cart = CartService.get_cart("ai-cart-session")
        self.assertEqual(len(persisted_cart["items"]), 1)
        self.assertEqual(persisted_cart["items"][0]["product_id"], "prod_nb_exec")
        self.assertEqual(persisted_cart["items"][0]["quantity"], 2)

    def test_20_transaction_failure_rollback(self):
        """Scenario 20: Transaction rollback on failure ensures database integrity."""
        # Initial cart state
        CartService.add_item("session-rollback", "prod_nb_exec", quantity=1, selected_variants={"sizes": "A5"})
        
        # Attempt operation that fails midway
        with self.assertRaises(ValueError):
            # Attempt to update to impossible quantity (exceeding stock)
            cart = CartService.get_cart("session-rollback")
            item_id = cart["items"][0]["id"]
            CartService.update_item("session-rollback", item_id, quantity=99999)

        # Cart must remain in original valid state
        clean_cart = CartService.get_cart("session-rollback")
        self.assertEqual(len(clean_cart["items"]), 1)
        self.assertEqual(clean_cart["items"][0]["quantity"], 1)
        self.assertEqual(clean_cart["subtotal"], 14.99)

if __name__ == "__main__":
    unittest.main()

