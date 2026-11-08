import unittest
import os
import json
from app.database.db import init_db, get_db
from app.services.catalogue_service import CatalogueService
from app.routes.products import get_products, get_product, get_categories
from fastapi import HTTPException

class TestCatalogue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Initialize database before tests."""
        init_db()

    def test_catalogue_seeded_minimum_count(self):
        """Test that catalogue contains at least 10 realistic products."""
        products = CatalogueService.get_all_products()
        self.assertGreaterEqual(len(products), 10, "Catalogue should contain at least 10 products.")

    def test_product_schema_fields(self):
        """Verify all required fields exist on products."""
        products = CatalogueService.get_all_products()
        required_fields = ["id", "name", "description", "category", "price", "stock", "variants", "image_url", "sku"]
        for p in products:
            for field in required_fields:
                self.assertIn(field, p, f"Product {p.get('id')} is missing field '{field}'")
            self.assertIsInstance(p["price"], (int, float))
            self.assertGreater(p["price"], 0)
            self.assertIsInstance(p["stock"], int)
            self.assertGreaterEqual(p["stock"], 0)
            self.assertIsInstance(p["variants"], dict)

    def test_categories_coverage(self):
        """Verify the expected hackathon categories are present."""
        categories = CatalogueService.get_categories()
        expected = ["Stationery", "Books", "Accessories", "Personalised Gifts"]
        for cat in expected:
            self.assertIn(cat, categories, f"Expected category '{cat}' not found in catalogue.")

    def test_filter_by_category(self):
        """Verify filtering products by category works accurately."""
        books = CatalogueService.get_all_products(category="Books")
        self.assertGreaterEqual(len(books), 2)
        for b in books:
            self.assertEqual(b["category"].lower(), "books")

    def test_search_products(self):
        """Verify search query matching."""
        results = CatalogueService.search_products("notebook")
        self.assertGreaterEqual(len(results), 1)
        self.assertTrue(any("notebook" in r["name"].lower() for r in results))

    def test_get_product_by_id(self):
        """Test retrieving product by valid ID."""
        product = CatalogueService.get_product_by_id("prod_nb_exec")
        self.assertIsNotNone(product)
        self.assertEqual(product["name"], "Executive Hardcover Notebook")
        self.assertEqual(product["sku"], "STAT-NBK-001")

    def test_get_product_invalid_id(self):
        """Test retrieving product by invalid ID returns None or raises 404 in route."""
        product = CatalogueService.get_product_by_id("non_existent_id")
        self.assertIsNone(product)
        
        with self.assertRaises(HTTPException) as ctx:
            get_product("non_existent_id")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_stock_checking(self):
        """Test inventory verification."""
        product = CatalogueService.get_product_by_id("prod_nb_exec")
        stock = product["stock"]
        
        has_stock, current = CatalogueService.check_stock("prod_nb_exec", 1)
        self.assertTrue(has_stock)
        self.assertEqual(current, stock)
        
        has_stock_excess, _ = CatalogueService.check_stock("prod_nb_exec", stock + 50)
        self.assertFalse(has_stock_excess)

    def test_variant_validation(self):
        """Test variant validation logic."""
        # Valid variant
        valid, err = CatalogueService.validate_variant("prod_nb_exec", {"sizes": "A5", "colors": "Classic Black"})
        self.assertTrue(valid, f"Variant validation failed: {err}")
        self.assertIsNone(err)

        # Invalid variant option
        invalid, err = CatalogueService.validate_variant("prod_nb_exec", {"sizes": "ExtraHugeA0"})
        self.assertFalse(invalid)
        self.assertIsNotNone(err)

    def test_api_route_handler(self):
        """Test API route handler returns ProductListResponse model."""
        res = get_products(category=None, search=None)
        self.assertGreaterEqual(res.total, 10)
        self.assertEqual(len(res.products), res.total)

if __name__ == "__main__":
    unittest.main()

