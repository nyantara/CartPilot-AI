import sqlite3
from typing import Dict, Any, List
from app.database.db import get_db
from app.services.order_service import OrderService

class DashboardService:
    @staticmethod
    def get_dashboard_summary() -> Dict[str, Any]:
        """
        Aggregate order metrics, payment statuses, gross revenue,
        and inventory alerts directly from the SQLite database.
        """
        with get_db() as conn:
            cursor = conn.cursor()

            # 1. Total order metrics
            cursor.execute("""
                SELECT
                    COUNT(*) as total_orders,
                    COALESCE(SUM(CASE WHEN payment_status = 'COMPLETED' THEN 1 ELSE 0 END), 0) as successful_payments,
                    COALESCE(SUM(CASE WHEN payment_status = 'PENDING' THEN 1 ELSE 0 END), 0) as pending_payments,
                    COALESCE(SUM(CASE WHEN payment_status = 'FAILED' THEN 1 ELSE 0 END), 0) as failed_payments,
                    COALESCE(SUM(CASE WHEN payment_status = 'CANCELLED' THEN 1 ELSE 0 END), 0) as cancelled_payments,
                    COALESCE(SUM(CASE WHEN payment_status = 'COMPLETED' THEN total_amount ELSE 0.0 END), 0.0) as total_sales
                FROM orders
            """)
            metrics_row = cursor.fetchone()

            total_orders = metrics_row["total_orders"] if metrics_row else 0
            successful_payments = metrics_row["successful_payments"] if metrics_row else 0
            pending_payments = metrics_row["pending_payments"] if metrics_row else 0
            failed_payments = metrics_row["failed_payments"] if metrics_row else 0
            cancelled_payments = metrics_row["cancelled_payments"] if metrics_row else 0
            total_sales = round(float(metrics_row["total_sales"]), 2) if metrics_row else 0.0

            # 2. Total products in catalogue
            cursor.execute("SELECT COUNT(*) as total_products FROM products")
            prod_count_row = cursor.fetchone()
            total_products = prod_count_row["total_products"] if prod_count_row else 0

            # 3. Low stock inventory alerts (products with stock <= 20)
            cursor.execute("""
                SELECT id, name, category, stock, sku
                FROM products
                WHERE stock <= 20
                ORDER BY stock ASC
                LIMIT 5
            """)
            low_stock_rows = cursor.fetchall()
            low_stock_alerts = [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "category": r["category"],
                    "stock": r["stock"],
                    "sku": r["sku"]
                }
                for r in low_stock_rows
            ]

        # 4. Recent orders with complete line item details
        recent_orders = OrderService.get_all_orders(limit=15)

        return {
            "total_orders": total_orders,
            "successful_payments": successful_payments,
            "pending_payments": pending_payments,
            "failed_payments": failed_payments,
            "cancelled_payments": cancelled_payments,
            "total_sales": total_sales,
            "currency": "USD",
            "recent_orders": recent_orders,
            "total_products": total_products,
            "low_stock_alerts": low_stock_alerts
        }

