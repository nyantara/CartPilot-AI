"""
Seed demo orders for Merchant Dashboard visualization and video recording.
Run with: python -m app.database.seed_demo_orders
"""

import sqlite3
import json
from datetime import datetime, timedelta
from app.database.db import get_db, init_db

DEMO_ORDERS = [
    {
        "id": "ord_demo_101",
        "session_id": "sess_demo_alex",
        "paypal_order_id": "5EF03303LY2624626",
        "paypal_capture_id": "CAP_981240182",
        "customer_name": "Alex Mercer",
        "customer_email": "alex.mercer@sandbox.buyer.com",
        "total_amount": 54.48,
        "currency": "USD",
        "payment_status": "COMPLETED",
        "created_at": (datetime.utcnow() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
        "items": [
            {
                "product_id": "prod_nb_exec",
                "product_name": "Executive Hardcover Notebook",
                "variant_details": {"sizes": "A5"},
                "quantity": 2,
                "unit_price": 14.99,
                "subtotal": 29.98
            },
            {
                "product_id": "prod_pnc_arch",
                "product_name": "Architect Drafting Mechanical Pencil (0.5mm)",
                "variant_details": {"colors": "Matte Black"},
                "quantity": 1,
                "unit_price": 12.50,
                "subtotal": 12.50
            },
            {
                "product_id": "prod_pen_gel",
                "product_name": "Minimalist Gel Ink Pen Set (0.5mm)",
                "variant_details": {"colors": "Blue"},
                "quantity": 1,
                "unit_price": 9.99,
                "subtotal": 9.99
            }
        ]
    },
    {
        "id": "ord_demo_102",
        "session_id": "sess_demo_sarah",
        "paypal_order_id": "9V901490VW455151X",
        "paypal_capture_id": "CAP_551029411",
        "customer_name": "Sarah Connor",
        "customer_email": "sarah.connor@sandbox.buyer.com",
        "total_amount": 84.49,
        "currency": "USD",
        "payment_status": "COMPLETED",
        "created_at": (datetime.utcnow() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S"),
        "items": [
            {
                "product_id": "prod_bk_ddia",
                "product_name": "Designing Data-Intensive Applications",
                "variant_details": {"formats": "Hardcover"},
                "quantity": 1,
                "unit_price": 44.50,
                "subtotal": 44.50
            },
            {
                "product_id": "prod_bk_pragmatic",
                "product_name": "The Pragmatic Programmer (20th Anniversary Edition)",
                "variant_details": {"formats": "Hardcover"},
                "quantity": 1,
                "unit_price": 39.99,
                "subtotal": 39.99
            }
        ]
    },
    {
        "id": "ord_demo_103",
        "session_id": "sess_demo_david",
        "paypal_order_id": "2K481940MM192840P",
        "paypal_capture_id": "CAP_119284055",
        "customer_name": "David Miller",
        "customer_email": "david.m@sandbox.buyer.com",
        "total_amount": 29.99,
        "currency": "USD",
        "payment_status": "COMPLETED",
        "created_at": (datetime.utcnow() - timedelta(hours=14)).strftime("%Y-%m-%d %H:%M:%S"),
        "items": [
            {
                "product_id": "prod_acc_deskmat",
                "product_name": "Full-Grain Vegan Leather Desk Mat",
                "variant_details": {"sizes": "Large (90x45cm)", "colors": "Cognac Brown"},
                "quantity": 1,
                "unit_price": 29.99,
                "subtotal": 29.99
            }
        ]
    },
    {
        "id": "ord_demo_104",
        "session_id": "sess_demo_elena",
        "paypal_order_id": "7L194019PP991823A",
        "paypal_capture_id": None,
        "customer_name": "Elena Rostova",
        "customer_email": "elena.r@sandbox.buyer.com",
        "total_amount": 34.99,
        "currency": "USD",
        "payment_status": "PENDING",
        "created_at": (datetime.utcnow() - timedelta(minutes=25)).strftime("%Y-%m-%d %H:%M:%S"),
        "items": [
            {
                "product_id": "prod_acc_stand",
                "product_name": "Ergonomic Aluminum Laptop Stand",
                "variant_details": {"colors": "Space Gray"},
                "quantity": 1,
                "unit_price": 34.99,
                "subtotal": 34.99
            }
        ]
    },
    {
        "id": "ord_demo_105",
        "session_id": "sess_demo_chris",
        "paypal_order_id": "3M882910CC441290Z",
        "paypal_capture_id": None,
        "customer_name": "Chris Evans",
        "customer_email": "chris.evans@sandbox.buyer.com",
        "total_amount": 22.00,
        "currency": "USD",
        "payment_status": "CANCELLED",
        "created_at": (datetime.utcnow() - timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"),
        "items": [
            {
                "product_id": "prod_gft_mug",
                "product_name": "Custom Monogram Ceramic Mug",
                "variant_details": {"colors": "Matte Cream"},
                "quantity": 1,
                "unit_price": 22.00,
                "subtotal": 22.00
            }
        ]
    }
]

def seed_demo_orders():
    init_db()
    with get_db() as conn:
        cursor = conn.cursor()

        print("Seeding sample orders for Merchant Dashboard demo...")
        seeded = 0
        for o in DEMO_ORDERS:
            cursor.execute("SELECT id FROM orders WHERE id = ?", (o["id"],))
            if cursor.fetchone():
                continue

            cursor.execute("""
                INSERT INTO orders (id, session_id, paypal_order_id, paypal_capture_id, customer_name, customer_email, total_amount, currency, payment_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                o["id"],
                o["session_id"],
                o["paypal_order_id"],
                o["paypal_capture_id"],
                o["customer_name"],
                o["customer_email"],
                o["total_amount"],
                o["currency"],
                o["payment_status"],
                o["created_at"],
                o["created_at"]
            ))

            for itm in o["items"]:
                cursor.execute("""
                    INSERT INTO order_items (order_id, product_id, product_name, variant_details, quantity, unit_price, subtotal)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    o["id"],
                    itm["product_id"],
                    itm["product_name"],
                    json.dumps(itm["variant_details"]),
                    itm["quantity"],
                    itm["unit_price"],
                    itm["subtotal"]
                ))
            seeded += 1

        print(f"Successfully ensured demo orders (inserted {seeded} new orders).")

if __name__ == "__main__":
    seed_demo_orders()
