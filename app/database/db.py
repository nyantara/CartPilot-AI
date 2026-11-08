import sqlite3
import json
from contextlib import contextmanager
from typing import Generator
from app.config import settings

def get_connection() -> sqlite3.Connection:
    """Create and return a new SQLite connection configured with Row factory."""
    conn = sqlite3.connect(settings.DATABASE_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for thread-safe database operations."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# Sample initial product catalogue
INITIAL_PRODUCTS = [
    {
        "id": "prod_nb_exec",
        "name": "Executive Hardcover Notebook",
        "description": "Premium 160-page dotted journal with 120gsm bleed-resistant ivory paper, dual ribbon bookmarks, and elastic closure.",
        "category": "Stationery",
        "price": 14.99,
        "stock": 40,
        "variants": json.dumps({"sizes": ["A4", "A5"], "colors": ["Classic Black", "Midnight Blue", "Emerald Green"]}),
        "image_url": "https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?auto=format&fit=crop&w=600&q=80",
        "sku": "STAT-NBK-001"
    },
    {
        "id": "prod_pen_gel",
        "name": "Minimalist Gel Ink Pen Set (Pack of 5)",
        "description": "Ultra-smooth 0.5mm Japanese archival ink pens with ergonomic matte rubber grip and quick-drying smear-free ink.",
        "category": "Stationery",
        "price": 9.99,
        "stock": 55,
        "variants": json.dumps({"colors": ["Black", "Blue", "Assorted Pack"]}),
        "image_url": "https://images.unsplash.com/photo-1583485088034-697b5bc54ccd?auto=format&fit=crop&w=600&q=80",
        "sku": "STAT-PEN-002"
    },
    {
        "id": "prod_pnc_arch",
        "name": "Architect Drafting Mechanical Pencil (0.5mm)",
        "description": "Full aluminum knurled grip drafting pencil with brass clutch mechanism and retractable tip protector.",
        "category": "Stationery",
        "price": 12.50,
        "stock": 25,
        "variants": json.dumps({"colors": ["Matte Black", "Silver", "Champagne Gold"]}),
        "image_url": "https://images.unsplash.com/photo-1585336261026-77884848d7c4?auto=format&fit=crop&w=600&q=80",
        "sku": "STAT-PNC-003"
    },
    {
        "id": "prod_stk_tabs",
        "name": "Pastel Sticky Notes & Index Tabs Bundle",
        "description": "Set of 8 self-adhesive memo pads and translucent PET index tabs in soothing muted aesthetic tones.",
        "category": "Stationery",
        "price": 6.99,
        "stock": 60,
        "variants": json.dumps({"palettes": ["Pastel Neon", "Earthy Muted"]}),
        "image_url": "https://images.unsplash.com/photo-1586075010923-2dd4570fb338?auto=format&fit=crop&w=600&q=80",
        "sku": "STAT-STK-004"
    },
    {
        "id": "prod_bk_pragmatic",
        "name": "The Pragmatic Programmer (20th Anniversary Edition)",
        "description": "The landmark software craftsmanship classic covering core engineering discipline, design patterns, and career excellence.",
        "category": "Books",
        "price": 39.99,
        "stock": 15,
        "variants": json.dumps({"formats": ["Hardcover", "Paperback"]}),
        "image_url": "https://images.unsplash.com/photo-1532012164546-f432f2e3777a?auto=format&fit=crop&w=600&q=80",
        "sku": "BOOK-PRG-005"
    },
    {
        "id": "prod_bk_ddia",
        "name": "Designing Data-Intensive Applications",
        "description": "Comprehensive distributed systems guide by Martin Kleppmann exploring reliable, scalable, and maintainable systems.",
        "category": "Books",
        "price": 44.50,
        "stock": 20,
        "variants": json.dumps({"formats": ["Hardcover", "Paperback"]}),
        "image_url": "https://images.unsplash.com/photo-1544947950-fa07a98d237f?auto=format&fit=crop&w=600&q=80",
        "sku": "BOOK-DDIA-006"
    },
    {
        "id": "prod_bk_atomic",
        "name": "Atomic Habits by James Clear",
        "description": "An easy and proven way to build good habits and break bad ones through tiny, compound behavioral shifts.",
        "category": "Books",
        "price": 18.00,
        "stock": 35,
        "variants": json.dumps({"formats": ["Hardcover", "Paperback"]}),
        "image_url": "https://images.unsplash.com/photo-1512820790803-83ca734da794?auto=format&fit=crop&w=600&q=80",
        "sku": "BOOK-ATM-007"
    },
    {
        "id": "prod_acc_deskmat",
        "name": "Full-Grain Vegan Leather Desk Mat",
        "description": "Spill-resistant, dual-sided desk pad that protects your tabletop and provides effortless mouse glide.",
        "category": "Accessories",
        "price": 29.99,
        "stock": 25,
        "variants": json.dumps({"sizes": ["Medium (80x40cm)", "Large (90x45cm)"], "colors": ["Cognac Brown", "Midnight Black"]}),
        "image_url": "https://images.unsplash.com/photo-1616628188859-7a11abb6fcc9?auto=format&fit=crop&w=600&q=80",
        "sku": "ACC-DMT-008"
    },
    {
        "id": "prod_acc_stand",
        "name": "Ergonomic Aluminum Laptop Stand",
        "description": "Precision CNC aluminum dual-pivot riser with heat dissipation vents, suitable for laptops up to 17 inches.",
        "category": "Accessories",
        "price": 34.99,
        "stock": 20,
        "variants": json.dumps({"colors": ["Space Gray", "Silver"]}),
        "image_url": "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?auto=format&fit=crop&w=600&q=80",
        "sku": "ACC-LST-009"
    },
    {
        "id": "prod_acc_pouch",
        "name": "Braided Cable Organizer & Tech Travel Pouch",
        "description": "Water-repellent travel case with elastic tension loops and padded compartments for cables, chargers, and accessories.",
        "category": "Accessories",
        "price": 15.99,
        "stock": 30,
        "variants": json.dumps({"colors": ["Charcoal Gray", "Olive Green"]}),
        "image_url": "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?auto=format&fit=crop&w=600&q=80",
        "sku": "ACC-CBL-010"
    },
    {
        "id": "prod_gft_journal",
        "name": "Custom Engraved Leather Journal",
        "description": "Refillable rustic leather travel journal personalized with precision laser-engraved monogram or name.",
        "category": "Personalised Gifts",
        "price": 24.99,
        "stock": 25,
        "variants": json.dumps({"colors": ["Rustic Tan", "Espresso Brown", "Deep Teal"]}),
        "image_url": "https://images.unsplash.com/photo-1517842645767-c639042777db?auto=format&fit=crop&w=600&q=80",
        "sku": "GFT-JRN-011"
    },
    {
        "id": "prod_gft_pen",
        "name": "Personalized Brass Rollerball Pen",
        "description": "Heavyweight solid brass executive writing pen custom-engraved with your recipient's name in an embossed gift box.",
        "category": "Personalised Gifts",
        "price": 21.99,
        "stock": 30,
        "variants": json.dumps({"finishes": ["Brushed Brass", "Matte Gunmetal"]}),
        "image_url": "https://images.unsplash.com/photo-1585336261026-77884848d7c4?auto=format&fit=crop&w=600&q=80",
        "sku": "GFT-PEN-012"
    },
    {
        "id": "prod_gft_bookmark",
        "name": "Custom Walnut Wood Bookmark Set",
        "description": "Hand-finished natural walnut wood bookmarks etched with custom botanical motifs, initials, or inspiring quotes.",
        "category": "Personalised Gifts",
        "price": 11.99,
        "stock": 45,
        "variants": json.dumps({"designs": ["Geometric", "Nature Floral", "Monogram Initials"]}),
        "image_url": "https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?auto=format&fit=crop&w=600&q=80",
        "sku": "GFT-BMK-013"
    }
]

def init_db() -> None:
    """Initialize database tables and seed sample data if empty."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Products table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER NOT NULL DEFAULT 0,
                variants TEXT NOT NULL DEFAULT '{}',
                image_url TEXT NOT NULL,
                sku TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 2. Orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                paypal_order_id TEXT UNIQUE,
                paypal_capture_id TEXT,
                customer_name TEXT,
                customer_email TEXT,
                total_amount REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                payment_status TEXT NOT NULL DEFAULT 'PENDING',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration: ensure session_id exists on orders
        cursor.execute("PRAGMA table_info(orders)")
        order_cols = [col["name"] for col in cursor.fetchall()]
        if "session_id" not in order_cols:
            cursor.execute("ALTER TABLE orders ADD COLUMN session_id TEXT")
        
        # 3. Order Items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                variant_details TEXT,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                subtotal REAL NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders (id)
            )
        """)

        # 4. Carts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS carts (
                id TEXT PRIMARY KEY,
                session_id TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Check cart_items table migration
        cursor.execute("PRAGMA table_info(cart_items)")
        columns = [col["name"] for col in cursor.fetchall()]
        if columns and "cart_id" not in columns:
            cursor.execute("DROP TABLE cart_items")

        # 5. Cart Items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cart_items (
                id TEXT PRIMARY KEY,
                cart_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                selected_variants TEXT NOT NULL DEFAULT '{}',
                unit_price REAL NOT NULL,
                subtotal REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cart_id) REFERENCES carts (id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products (id)
            )
        """)
        
        # Check if products exist; if not, seed initial products
        cursor.execute("SELECT COUNT(*) as count FROM products")
        count = cursor.fetchone()["count"]
        
        if count == 0:
            for p in INITIAL_PRODUCTS:
                cursor.execute("""
                    INSERT INTO products (id, name, description, category, price, stock, variants, image_url, sku)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    p["id"],
                    p["name"],
                    p["description"],
                    p["category"],
                    p["price"],
                    p["stock"],
                    p["variants"],
                    p["image_url"],
                    p["sku"]
                ))
