import unittest
from fastapi import HTTPException

from app.database.db import init_db, get_db
from app.routes.cart import (
    get_cart,
    add_item_to_cart,
    update_cart_item,
    remove_cart_item,
    clear_cart
)
from app.schemas.cart import AddToCartItemRequest, UpdateCartItemRequest

class TestCartAPIRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        with get_db() as conn:
            conn.execute("DELETE FROM cart_items")
            conn.execute("DELETE FROM carts")

    def test_cart_api_crud_lifecycle(self):
        """Test full CRUD lifecycle through route handlers."""
        session_id = "api-session-crud"

        # 1. GET empty cart
        empty_cart = get_cart(session_id)
        self.assertEqual(empty_cart.session_id, session_id)
        self.assertEqual(len(empty_cart.items), 0)
        self.assertEqual(empty_cart.subtotal, 0.0)

        # 2. POST add item
        add_req = AddToCartItemRequest(
            product_id="prod_nb_exec",
            quantity=2,
            selected_variants={"sizes": "A5"}
        )
        cart_after_add = add_item_to_cart(session_id, add_req)
        self.assertEqual(len(cart_after_add.items), 1)
        self.assertEqual(cart_after_add.items[0].quantity, 2)
        self.assertEqual(cart_after_add.subtotal, 29.98)

        item_id = cart_after_add.items[0].id

        # 3. PATCH update quantity
        update_req = UpdateCartItemRequest(quantity=3)
        cart_after_update = update_cart_item(session_id, item_id, update_req)
        self.assertEqual(cart_after_update.items[0].quantity, 3)
        self.assertEqual(cart_after_update.subtotal, 44.97)

        # 4. DELETE single item
        cart_after_delete_item = remove_cart_item(session_id, item_id)
        self.assertEqual(len(cart_after_delete_item.items), 0)
        self.assertEqual(cart_after_delete_item.subtotal, 0.0)

        # 5. POST another item and DELETE clear cart
        add_item_to_cart(session_id, AddToCartItemRequest(product_id="prod_pen_gel", quantity=1))
        cart_cleared = clear_cart(session_id)
        self.assertEqual(len(cart_cleared.items), 0)

    def test_cart_api_error_handling(self):
        """Test proper HTTP status codes for invalid input."""
        session_id = "api-errors"

        # Nonexistent product -> 404
        with self.assertRaises(HTTPException) as ctx:
            add_item_to_cart(session_id, AddToCartItemRequest(product_id="fake_product", quantity=1))
        self.assertEqual(ctx.exception.status_code, 404)

        # Exceeding stock -> 400
        with self.assertRaises(HTTPException) as ctx:
            add_item_to_cart(session_id, AddToCartItemRequest(product_id="prod_acc_stand", quantity=999))
        self.assertEqual(ctx.exception.status_code, 400)

        # Nonexistent item update -> 404
        with self.assertRaises(HTTPException) as ctx:
            update_cart_item(session_id, "non_existent_item_id", UpdateCartItemRequest(quantity=1))
        self.assertEqual(ctx.exception.status_code, 404)

if __name__ == "__main__":
    unittest.main()

