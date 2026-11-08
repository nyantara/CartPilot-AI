import json
import sqlite3
import uuid
import logging
from typing import Dict, List, Optional, Any, Tuple
from app.config import settings
from app.database.db import get_db
from app.services.catalogue_service import CatalogueService
from app.services.cart_service import CartService
from app.services.paypal_service import PayPalService, PayPalAPIError

logger = logging.getLogger(__name__)

class OrderService:
    @staticmethod
    def create_order_from_cart(
        session_id: str,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
        paypal_client_override: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Validate the customer's cart, recheck live inventory and prices,
        create a PayPal v2 order, and record the draft order in SQLite.
        """
        # 1. Fetch persistent cart
        cart = CartService.get_cart(session_id)
        if not cart or len(cart["items"]) == 0:
            raise ValueError("Cannot initiate checkout with an empty shopping cart.")

        # 2. Strict backend verification of stock and authoritative pricing
        verified_items = []
        calculated_total = 0.0

        for item in cart["items"]:
            product = CatalogueService.get_product_by_id(item["product_id"])
            if not product:
                raise KeyError(f"Product '{item['product_name']}' is no longer available.")
            if item["quantity"] > product["stock"]:
                raise ValueError(
                    f"Insufficient stock for '{product['name']}'. Requested {item['quantity']}, "
                    f"but only {product['stock']} available."
                )

            # Price from SQLite products table
            authoritative_unit_price = round(float(product["price"]), 2)
            item_subtotal = round(authoritative_unit_price * item["quantity"], 2)
            calculated_total += item_subtotal

            verified_items.append({
                "product_id": product["id"],
                "product_name": product["name"],
                "sku": product["sku"],
                "variant_details": item["selected_variants"],
                "quantity": item["quantity"],
                "unit_price": authoritative_unit_price,
                "subtotal": item_subtotal
            })

        calculated_total = round(calculated_total, 2)
        internal_order_id = f"ord_{uuid.uuid4().hex[:12]}"
        currency = settings.PAYPAL_CURRENCY

        # 3. Create PayPal Sandbox Order
        if paypal_client_override:
            paypal_order = paypal_client_override.create_order(
                internal_order_id=internal_order_id,
                total_amount=calculated_total,
                currency=currency,
                items=verified_items,
                custom_id=session_id
            )
        else:
            paypal_order = PayPalService.create_order(
                internal_order_id=internal_order_id,
                total_amount=calculated_total,
                currency=currency,
                items=verified_items,
                custom_id=session_id
            )

        paypal_order_id = paypal_order["id"]

        # 4. Atomically persist draft order and snapshot items into SQLite
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO orders (id, session_id, paypal_order_id, customer_name, customer_email, total_amount, currency, payment_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
            """, (
                internal_order_id,
                session_id,
                paypal_order_id,
                customer_name,
                customer_email,
                calculated_total,
                currency
            ))

            for item in verified_items:
                cursor.execute("""
                    INSERT INTO order_items (order_id, product_id, product_name, variant_details, quantity, unit_price, subtotal)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    internal_order_id,
                    item["product_id"],
                    item["product_name"],
                    json.dumps(item["variant_details"]),
                    item["quantity"],
                    item["unit_price"],
                    item["subtotal"]
                ))

        return {
            "order_id": internal_order_id,
            "paypal_order_id": paypal_order_id,
            "total_amount": calculated_total,
            "currency": currency,
            "status": "PENDING"
        }

    @staticmethod
    def capture_and_finalize_order(
        order_identifier: str,
        session_id: Optional[str] = None,
        paypal_client_override: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Capture approved payment via PayPal Orders API v2, verify captured amount & currency,
        safely decrement inventory in an atomic transaction, and mark order COMPLETED.
        Includes idempotency protection against duplicate captures.
        """
        # 1. Retrieve order by internal order ID or PayPal Order ID
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM orders WHERE id = ? OR paypal_order_id = ?
            """, (order_identifier, order_identifier))
            order_row = cursor.fetchone()

        if not order_row:
            raise KeyError(f"Order '{order_identifier}' not found in database.")

        order = dict(order_row)
        order_id = order["id"]
        paypal_order_id = order["paypal_order_id"]
        expected_amount = round(float(order["total_amount"]), 2)
        expected_currency = order["currency"].upper()

        # Session isolation check if provided
        if session_id and order.get("session_id") and order["session_id"] != session_id:
            raise KeyError(f"Order '{order_id}' does not belong to session '{session_id}'.")

        # 2. Idempotency Check: if order is already COMPLETED, return without double-capture or double-stock deduction
        if order["payment_status"] == "COMPLETED":
            logger.info(f"Order '{order_id}' already marked COMPLETED. Returning idempotent response.")
            return {
                "order_id": order_id,
                "paypal_order_id": paypal_order_id,
                "capture_id": order.get("paypal_capture_id"),
                "status": "COMPLETED",
                "amount_captured": expected_amount,
                "currency": expected_currency,
                "customer_name": order.get("customer_name"),
                "customer_email": order.get("customer_email"),
                "message": "Order was already successfully captured."
            }

        if order["payment_status"] == "CANCELLED":
            raise ValueError(f"Cannot capture cancelled order '{order_id}'.")

        # 3. Call PayPal to capture payment
        if paypal_client_override:
            capture_resp = paypal_client_override.capture_order(paypal_order_id)
        else:
            try:
                capture_resp = PayPalService.capture_order(paypal_order_id)
            except PayPalAPIError as pae:
                err_text = str(pae)
                if "ORDER_NOT_APPROVED" in err_text:
                    raise ValueError("Payment approval required: The buyer has not yet approved the order in the PayPal window.")
                if "INSTRUMENT_DECLINED" in err_text:
                    raise ValueError("Payment method was declined by PayPal. Please select a different payment method in your PayPal account.")
                raise

        # 4. Response & Amount Verification
        overall_status = capture_resp.get("status", "")
        purchase_units = capture_resp.get("purchase_units", [])
        if not purchase_units:
            raise ValueError("Invalid PayPal capture response: missing purchase units.")

        captures = purchase_units[0].get("payments", {}).get("captures", [])
        if not captures:
            raise ValueError("No payment captures found in PayPal response.")

        primary_capture = captures[0]
        capture_status = primary_capture.get("status", "")
        capture_id = primary_capture.get("id")
        amount_val = float(primary_capture.get("amount", {}).get("value", 0.0))
        currency_code = primary_capture.get("amount", {}).get("currency_code", "").upper()

        # Payer information from PayPal response
        payer = capture_resp.get("payer", {})
        payer_name = None
        if "name" in payer:
            payer_name = f"{payer['name'].get('given_name', '')} {payer['name'].get('surname', '')}".strip()
        payer_email = payer.get("email_address")

        if capture_status != "COMPLETED":
            # Mark order as FAILED in database without deducting stock
            with get_db() as conn:
                conn.execute(
                    "UPDATE orders SET payment_status = 'FAILED', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (order_id,)
                )
            raise ValueError(f"Payment capture was not completed by PayPal. Status: {capture_status}")

        # Strict amount check: captured amount must match internal order
        if abs(amount_val - expected_amount) > 0.01:
            with get_db() as conn:
                conn.execute(
                    "UPDATE orders SET payment_status = 'FAILED', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (order_id,)
                )
            raise ValueError(
                f"Fraud detection / Amount mismatch: Captured amount ${amount_val:.2f} does not match "
                f"order total ${expected_amount:.2f}."
            )

        if currency_code != expected_currency:
            with get_db() as conn:
                conn.execute(
                    "UPDATE orders SET payment_status = 'FAILED', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (order_id,)
                )
            raise ValueError(
                f"Currency mismatch: Captured currency {currency_code} does not match expected {expected_currency}."
            )

        # 5. ATOMIC DATABASE TRANSACTION: Deduct inventory, update order, clear cart
        with get_db() as conn:
            cursor = conn.cursor()

            # Retrieve line items to decrement stock
            cursor.execute("SELECT product_id, quantity, product_name FROM order_items WHERE order_id = ?", (order_id,))
            items = cursor.fetchall()

            for itm in items:
                # Concurrency-safe decrement with non-negative check
                cursor.execute("SELECT stock FROM products WHERE id = ?", (itm["product_id"],))
                prod_row = cursor.fetchone()
                if not prod_row or prod_row["stock"] < itm["quantity"]:
                    raise ValueError(
                        f"Stock conflict: Insufficient inventory for '{itm['product_name']}'. "
                        f"Available: {prod_row['stock'] if prod_row else 0}, Required: {itm['quantity']}."
                    )

                cursor.execute("""
                    UPDATE products
                    SET stock = stock - ?
                    WHERE id = ? AND stock >= ?
                """, (itm["quantity"], itm["product_id"], itm["quantity"]))

            # Update order to COMPLETED
            customer_name_final = payer_name or order.get("customer_name")
            customer_email_final = payer_email or order.get("customer_email")

            cursor.execute("""
                UPDATE orders
                SET payment_status = 'COMPLETED',
                    paypal_capture_id = ?,
                    customer_name = ?,
                    customer_email = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (capture_id, customer_name_final, customer_email_final, order_id))

            # Empty session cart upon completed order
            if order.get("session_id"):
                sess = order["session_id"]
                cursor.execute("""
                    DELETE FROM cart_items WHERE cart_id IN (SELECT id FROM carts WHERE session_id = ?)
                """, (sess,))
                cursor.execute("""
                    UPDATE carts SET updated_at = CURRENT_TIMESTAMP WHERE session_id = ?
                """, (sess,))

        return {
            "order_id": order_id,
            "paypal_order_id": paypal_order_id,
            "capture_id": capture_id,
            "status": "COMPLETED",
            "amount_captured": amount_val,
            "currency": currency_code,
            "customer_name": customer_name_final,
            "customer_email": customer_email_final,
            "message": "Payment captured and order verified successfully."
        }

    @staticmethod
    def cancel_order(order_identifier: str) -> Dict[str, Any]:
        """Mark an order as CANCELLED when the customer aborts the PayPal modal."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM orders WHERE id = ? OR paypal_order_id = ?
            """, (order_identifier, order_identifier))
            order = cursor.fetchone()
            if not order:
                raise KeyError(f"Order '{order_identifier}' not found.")

            if order["payment_status"] == "COMPLETED":
                raise ValueError("Cannot cancel an already completed order.")

            cursor.execute("""
                UPDATE orders SET payment_status = 'CANCELLED', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (order["id"],))

        return {
            "order_id": order["id"],
            "paypal_order_id": order["paypal_order_id"],
            "status": "CANCELLED",
            "message": "Order payment was cancelled by customer."
        }

    @staticmethod
    def get_order(order_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full details of an order along with its line items."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE id = ? OR paypal_order_id = ?", (order_id, order_id))
            order_row = cursor.fetchone()
            if not order_row:
                return None

            order = dict(order_row)
            cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (order["id"],))
            items_rows = cursor.fetchall()
            
            items = []
            for r in items_rows:
                d = dict(r)
                try:
                    d["variant_details"] = json.loads(d["variant_details"])
                except Exception:
                    d["variant_details"] = {}
                items.append(d)

            order["items"] = items
            return order

    @staticmethod
    def get_orders_by_session(session_id: str) -> List[Dict[str, Any]]:
        """Retrieve all orders placed under a specific session."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM orders WHERE session_id = ? ORDER BY created_at DESC", (session_id,))
            order_ids = [r["id"] for r in cursor.fetchall()]
            
        return [OrderService.get_order(oid) for oid in order_ids if oid]

    @staticmethod
    def get_all_orders(limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent orders for the merchant dashboard."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM orders ORDER BY created_at DESC LIMIT ?", (limit,))
            order_ids = [r["id"] for r in cursor.fetchall()]
            
        return [OrderService.get_order(oid) for oid in order_ids if oid]
