import json
import sqlite3
import uuid
from typing import Dict, List, Optional, Any, Tuple
from app.database.db import get_db
from app.services.catalogue_service import CatalogueService
from app.services.conversation_service import ConversationService

def _canonical_variants_json(variants: Dict[str, str]) -> str:
    """Serialize variants dict deterministically with sorted keys."""
    if not variants:
        return "{}"
    return json.dumps({k.strip().lower(): v.strip() for k, v in sorted(variants.items())})

class CartService:
    @staticmethod
    def get_or_create_cart(session_id: str, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        """
        Retrieve the active cart for a session, or create one if it does not exist.
        Ensures strictly one active cart per session.
        """
        def _execute(db_conn: sqlite3.Connection) -> Dict[str, Any]:
            cursor = db_conn.cursor()
            cursor.execute("SELECT * FROM carts WHERE session_id = ? AND status = 'ACTIVE'", (session_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
                
            cart_id = f"cart_{uuid.uuid4().hex[:12]}"
            cursor.execute("""
                INSERT INTO carts (id, session_id, status)
                VALUES (?, ?, 'ACTIVE')
            """, (cart_id, session_id))
            
            cursor.execute("SELECT * FROM carts WHERE id = ?", (cart_id,))
            return dict(cursor.fetchone())

        if conn is not None:
            return _execute(conn)
        with get_db() as db_conn:
            return _execute(db_conn)

    @staticmethod
    def get_cart(session_id: str) -> Dict[str, Any]:
        """
        Retrieve full cart details for a session.
        Calculates authoritative totals and item subtotals directly from catalogue prices.
        """
        with get_db() as conn:
            cart = CartService.get_or_create_cart(session_id, conn=conn)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT ci.id, ci.cart_id, ci.product_id, ci.quantity, ci.selected_variants,
                       ci.unit_price, ci.subtotal, ci.created_at, ci.updated_at,
                       p.name as product_name, p.category, p.price as current_db_price,
                       p.stock as current_stock, p.image_url, p.sku
                FROM cart_items ci
                JOIN products p ON ci.product_id = p.id
                WHERE ci.cart_id = ?
                ORDER BY ci.created_at ASC
            """, (cart["id"],))
            
            rows = cursor.fetchall()
            items: List[Dict[str, Any]] = []
            total_items = 0
            cart_subtotal = 0.0
            
            for r in rows:
                qty = r["quantity"]
                # Authoritative pricing from products table
                unit_price = round(float(r["current_db_price"]), 2)
                item_subtotal = round(unit_price * qty, 2)
                
                try:
                    variants_dict = json.loads(r["selected_variants"])
                except Exception:
                    variants_dict = {}
                    
                items.append({
                    "id": r["id"],
                    "cart_id": r["cart_id"],
                    "product_id": r["product_id"],
                    "product_name": r["product_name"],
                    "category": r["category"],
                    "quantity": qty,
                    "selected_variants": variants_dict,
                    "unit_price": unit_price,
                    "subtotal": item_subtotal,
                    "image_url": r["image_url"],
                    "sku": r["sku"],
                    "stock_available": r["current_stock"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"]
                })
                total_items += qty
                cart_subtotal += item_subtotal

            cart_subtotal = round(cart_subtotal, 2)
            
            # Check budget constraints from session context
            context = ConversationService.get_context(session_id)
            budget = context.get("current_budget")
            budget_exceeded = False
            budget_alert = None
            if budget is not None and cart_subtotal > budget:
                budget_exceeded = True
                budget_alert = f"Cart total (${cart_subtotal:.2f}) exceeds your stated budget of ${budget:.2f}."

            return {
                "id": cart["id"],
                "session_id": session_id,
                "status": cart["status"],
                "items": items,
                "total_items": total_items,
                "subtotal": cart_subtotal,
                "currency": "USD",
                "budget": budget,
                "budget_exceeded": budget_exceeded,
                "budget_alert": budget_alert,
                "created_at": cart.get("created_at"),
                "updated_at": cart.get("updated_at")
            }

    @staticmethod
    def add_item(
        session_id: str,
        product_id: str,
        quantity: int = 1,
        selected_variants: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Add an item to the session cart.
        - Validates quantity > 0.
        - Validates product existence against SQLite catalogue.
        - Validates variants against catalogue rules.
        - Validates stock availability.
        - Merges quantities if product with identical variants already exists.
        - Atomically persists using database transactions.
        """
        if quantity <= 0:
            raise ValueError(f"Quantity must be greater than zero. Received: {quantity}")

        # 1. Product existence check
        product = CatalogueService.get_product_by_id(product_id)
        if not product:
            raise KeyError(f"Product '{product_id}' was not found in the catalogue.")

        # 2. Variant validation
        resolved_variants, variant_err, is_missing_choice = CatalogueService.resolve_variants(
            product, selected_variants or {}
        )
        if variant_err and not is_missing_choice:
            raise ValueError(variant_err)
        if is_missing_choice:
            raise ValueError(variant_err)

        canonical_var_str = _canonical_variants_json(resolved_variants)
        authoritative_price = round(float(product["price"]), 2)

        # 3. Transactional insert or update
        with get_db() as conn:
            cart = CartService.get_or_create_cart(session_id, conn=conn)
            cursor = conn.cursor()
            
            # Check for existing item with identical product_id and variants
            cursor.execute("""
                SELECT id, quantity FROM cart_items
                WHERE cart_id = ? AND product_id = ? AND selected_variants = ?
            """, (cart["id"], product_id, canonical_var_str))
            
            existing = cursor.fetchone()
            
            if existing:
                item_id = existing["id"]
                new_qty = existing["quantity"] + quantity
                
                # Stock validation for cumulative quantity
                if new_qty > product["stock"]:
                    raise ValueError(
                        f"Cannot add {quantity} more. Stock limit reached: {new_qty} requested, "
                        f"but only {product['stock']} available."
                    )
                    
                new_subtotal = round(authoritative_price * new_qty, 2)
                cursor.execute("""
                    UPDATE cart_items
                    SET quantity = ?, unit_price = ?, subtotal = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (new_qty, authoritative_price, new_subtotal, item_id))
            else:
                # Stock validation for initial addition
                if quantity > product["stock"]:
                    raise ValueError(
                        f"Insufficient stock. Requested {quantity}, but only {product['stock']} units available."
                    )
                    
                item_id = f"item_{uuid.uuid4().hex[:12]}"
                subtotal = round(authoritative_price * quantity, 2)
                cursor.execute("""
                    INSERT INTO cart_items (id, cart_id, product_id, quantity, selected_variants, unit_price, subtotal)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (item_id, cart["id"], product_id, quantity, canonical_var_str, authoritative_price, subtotal))

            # Update parent cart timestamp
            cursor.execute("UPDATE carts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (cart["id"],))

        return CartService.get_cart(session_id)

    @staticmethod
    def update_item(
        session_id: str,
        item_id: str,
        quantity: Optional[int] = None,
        selected_variants: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Update quantity or variants of an existing cart item.
        - Rejects quantity <= 0.
        - Validates stock limits.
        - Validates updated variants.
        """
        if quantity is not None and quantity <= 0:
            raise ValueError(f"Quantity must be greater than zero. Received: {quantity}")

        with get_db() as conn:
            cart = CartService.get_or_create_cart(session_id, conn=conn)
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM cart_items WHERE id = ? AND cart_id = ?", (item_id, cart["id"]))
            item = cursor.fetchone()
            if not item:
                raise KeyError(f"Cart item '{item_id}' not found in cart.")

            product = CatalogueService.get_product_by_id(item["product_id"])
            if not product:
                raise KeyError(f"Product '{item['product_id']}' no longer exists.")

            target_qty = quantity if quantity is not None else item["quantity"]
            if target_qty > product["stock"]:
                raise ValueError(
                    f"Insufficient stock. Requested {target_qty}, but only {product['stock']} units available."
                )

            target_var_str = item["selected_variants"]
            if selected_variants is not None:
                resolved_var, var_err, is_missing = CatalogueService.resolve_variants(product, selected_variants)
                if var_err:
                    raise ValueError(var_err)
                target_var_str = _canonical_variants_json(resolved_var)

            authoritative_price = round(float(product["price"]), 2)
            new_subtotal = round(authoritative_price * target_qty, 2)

            cursor.execute("""
                UPDATE cart_items
                SET quantity = ?, selected_variants = ?, unit_price = ?, subtotal = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (target_qty, target_var_str, authoritative_price, new_subtotal, item_id))

            cursor.execute("UPDATE carts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (cart["id"],))

        return CartService.get_cart(session_id)

    @staticmethod
    def remove_item(session_id: str, item_id: str) -> Dict[str, Any]:
        """Remove a specific item from the session's cart."""
        with get_db() as conn:
            cart = CartService.get_or_create_cart(session_id, conn=conn)
            cursor = conn.cursor()
            
            cursor.execute("SELECT id FROM cart_items WHERE id = ? AND cart_id = ?", (item_id, cart["id"]))
            if not cursor.fetchone():
                raise KeyError(f"Cart item '{item_id}' not found in cart.")

            cursor.execute("DELETE FROM cart_items WHERE id = ?", (item_id,))
            cursor.execute("UPDATE carts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (cart["id"],))

        return CartService.get_cart(session_id)

    @staticmethod
    def clear_cart(session_id: str) -> Dict[str, Any]:
        """Empty all items from the session's active cart."""
        with get_db() as conn:
            cart = CartService.get_or_create_cart(session_id, conn=conn)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cart_items WHERE cart_id = ?", (cart["id"],))
            cursor.execute("UPDATE carts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (cart["id"],))

        return CartService.get_cart(session_id)

    @staticmethod
    def validate_cart(session_id: str) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Validate live inventory and pricing for all items in the cart.
        Returns: (is_valid, error_list, current_cart_dict).
        """
        cart = CartService.get_cart(session_id)
        errors: List[str] = []
        
        for item in cart["items"]:
            product = CatalogueService.get_product_by_id(item["product_id"])
            if not product:
                errors.append(f"Product '{item['product_name']}' is no longer available.")
                continue
            if item["quantity"] > product["stock"]:
                errors.append(
                    f"Insufficient stock for '{item['product_name']}': {item['quantity']} in cart, "
                    f"but only {product['stock']} currently available."
                )
                
        return len(errors) == 0, errors, cart

