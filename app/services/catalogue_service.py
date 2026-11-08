import json
import sqlite3
import re
from typing import List, Dict, Any, Optional, Tuple
from app.database.db import get_db

def _row_to_product_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Helper to convert a sqlite Row to a dict and deserialize variants JSON."""
    d = dict(row)
    if "variants" in d and isinstance(d["variants"], str):
        try:
            d["variants"] = json.loads(d["variants"])
        except Exception:
            d["variants"] = {}
    return d

STOP_WORDS = {
    "a", "an", "the", "and", "or", "of", "in", "for", "with", "to", "at",
    "i", "need", "want", "please", "can", "you", "give", "me", "add", "buy",
    "item", "items", "product", "products", "one", "two", "three", "four", "five"
}

class CatalogueService:
    @staticmethod
    def get_all_products(category: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve all products, optionally filtered by category or search term."""
        query = "SELECT * FROM products WHERE 1=1"
        params = []
        
        if category:
            query += " AND LOWER(category) = LOWER(?)"
            params.append(category)
            
        if search:
            query += " AND (LOWER(name) LIKE LOWER(?) OR LOWER(description) LIKE LOWER(?))"
            wildcard = f"%{search}%"
            params.extend([wildcard, wildcard])
            
        query += " ORDER BY category ASC, name ASC"
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [_row_to_product_dict(r) for r in rows]

    @staticmethod
    def get_product_by_id(product_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific product by ID."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return _row_to_product_dict(row)

    @staticmethod
    def get_categories() -> List[str]:
        """Retrieve distinct product categories."""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT category FROM products ORDER BY category ASC")
            rows = cursor.fetchall()
            return [r["category"] for r in rows]

    @staticmethod
    def search_products(query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Simple text search over product catalogue."""
        wildcard = f"%{query}%"
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM products
                WHERE LOWER(name) LIKE LOWER(?) OR LOWER(description) LIKE LOWER(?) OR LOWER(category) LIKE LOWER(?)
                LIMIT ?
            """, (wildcard, wildcard, wildcard, limit))
            rows = cursor.fetchall()
            return [_row_to_product_dict(r) for r in rows]

    @staticmethod
    def check_stock(product_id: str, requested_quantity: int) -> Tuple[bool, int]:
        """Check if sufficient stock is available. Returns (is_available, available_stock)."""
        product = CatalogueService.get_product_by_id(product_id)
        if not product:
            return False, 0
        current_stock = product.get("stock", 0)
        return current_stock >= requested_quantity, current_stock

    @staticmethod
    def validate_variant(product_id: str, selected_variant: Dict[str, str]) -> Tuple[bool, Optional[str]]:
        """
        Validate whether the selected variant options exist for the product.
        Returns (is_valid, error_message).
        """
        product = CatalogueService.get_product_by_id(product_id)
        if not product:
            return False, f"Product '{product_id}' not found."
            
        available_variants = product.get("variants", {})
        if not available_variants and not selected_variant:
            return True, None
            
        for key, val in selected_variant.items():
            matched_key = None
            for avail_key in available_variants.keys():
                if avail_key.lower() == key.lower() or avail_key.lower().rstrip('s') == key.lower().rstrip('s'):
                    matched_key = avail_key
                    break
                    
            if not matched_key:
                return False, f"Variant option '{key}' is not available for '{product['name']}'."
                
            valid_options = available_variants[matched_key]
            if not any(v.lower() == val.lower() or val.lower() in v.lower() for v in valid_options):
                return False, f"Option '{val}' is not valid for {key}. Available: {', '.join(valid_options)}."
                
        return True, None

    @staticmethod
    def match_product_query(query: str) -> List[Tuple[Dict[str, Any], float]]:
        """
        Grounding matcher: Match a user's natural query against the real catalogue.
        Returns list of (product_dict, confidence_score) sorted by highest confidence.
        """
        if not query or not query.strip():
            return []
            
        clean_query = query.strip().lower()
        all_products = CatalogueService.get_all_products()
        matches: List[Tuple[Dict[str, Any], float]] = []

        # 1. Exact ID or SKU check
        for p in all_products:
            if clean_query == p["id"].lower() or clean_query == p["sku"].lower():
                return [(p, 1.0)]

        # 2. Tokenize user query
        tokens = [t for t in re.findall(r'\b[a-zA-Z0-9_-]+\b', clean_query) if t not in STOP_WORDS]
        if not tokens:
            tokens = clean_query.split()

        for p in all_products:
            name_lower = p["name"].lower()
            desc_lower = p["description"].lower()
            cat_lower = p["category"].lower()
            sku_lower = p["sku"].lower()
            
            score = 0.0
            
            # Exact name match or substring
            if name_lower == clean_query:
                score += 1.0
            elif clean_query in name_lower:
                score += 0.85
            elif name_lower in clean_query:
                score += 0.80
                
            # Category match (e.g. user says "I need a book")
            if cat_lower == clean_query or (len(tokens) == 1 and tokens[0] == cat_lower.rstrip('s')):
                score += 0.65

            # Token overlap scoring
            token_matches = 0
            for t in tokens:
                if t in name_lower:
                    token_matches += 1.5
                elif t in desc_lower:
                    token_matches += 0.5
                elif t in cat_lower:
                    token_matches += 0.8
                elif t in sku_lower:
                    token_matches += 1.0
                    
            if token_matches > 0:
                normalized_token_score = min(token_matches / (len(tokens) + 0.5), 0.9)
                score = max(score, normalized_token_score)

            if score >= 0.4:
                matches.append((p, round(score, 3)))

        # Sort descending by match score
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches

    @staticmethod
    def resolve_variants(product: Dict[str, Any], requested_variant: Dict[str, str]) -> Tuple[Dict[str, str], Optional[str], bool]:
        """
        Normalize and validate extracted variants against product catalogue.
        Supports both key-value pairs (e.g. {"sizes": "A5"}) and bare values (e.g. {"option": "A5"}).
        Returns:
            - resolved_variants: Dict[str, str]
            - clarification_or_error: Optional[str]
            - is_missing_required_choice: bool
        """
        available_variants = product.get("variants", {})
        if not available_variants:
            return {}, None, False

        resolved: Dict[str, str] = {}

        for req_k, req_v in requested_variant.items():
            if not req_v:
                continue
            req_k_clean = req_k.lower().strip()
            matched_key = None
            matched_val = None
            
            # 1. Match by key name (size -> sizes, color -> colors, etc.)
            for avail_k in available_variants.keys():
                if avail_k.lower() == req_k_clean or avail_k.lower().rstrip('s') == req_k_clean.rstrip('s'):
                    matched_key = avail_k
                    break
                    
            if matched_key:
                # Check value against options under matched key
                valid_options = available_variants[matched_key]
                for opt in valid_options:
                    if opt.lower() == req_v.lower() or req_v.lower() in opt.lower() or opt.lower() in req_v.lower():
                        matched_val = opt
                        break
                if not matched_val:
                    return resolved, f"Option '{req_v}' is not valid for {matched_key}. Available: {', '.join(valid_options)}.", False
                resolved[matched_key] = matched_val
            else:
                # 2. Value-first match: check if req_v directly matches any option in ANY category
                for avail_k, valid_options in available_variants.items():
                    for opt in valid_options:
                        if opt.lower() == req_v.lower() or req_v.lower() in opt.lower() or opt.lower() in req_v.lower():
                            matched_key = avail_k
                            matched_val = opt
                            break
                    if matched_key:
                        break
                        
                if matched_key and matched_val:
                    resolved[matched_key] = matched_val
                else:
                    return resolved, f"Variant '{req_k}' ('{req_v}') is not available for {product['name']}.", False

        # Check if there is a primary variant with multiple options that wasn't specified
        for k, options in available_variants.items():
            if k not in resolved and len(options) > 1 and k.lower() in ["sizes", "formats"]:
                clarification = f"For {product['name']}, what {k.rstrip('s')} would you prefer: {', '.join(options)}?"
                return resolved, clarification, True

        return resolved, None, False

    @staticmethod
    def get_catalogue_summary_for_ai() -> str:
        """Generate a concise string representation of the catalogue for AI prompting."""
        products = CatalogueService.get_all_products()
        lines = []
        for p in products:
            var_str = ""
            if p.get("variants"):
                var_str = f" | Variants: {json.dumps(p['variants'])}"
            lines.append(
                f"- [ID: {p['id']}] {p['name']} | Category: {p['category']} | Price: ${p['price']:.2f} | Stock: {p['stock']}{var_str}"
            )
        return "\n".join(lines)
