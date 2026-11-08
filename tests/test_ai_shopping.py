import unittest
import os
import json
from unittest.mock import MagicMock, patch

from app.database.db import init_db
from app.config import settings
from app.schemas.chat import StructuredAIOutput, ExtractedItem
from app.services.catalogue_service import CatalogueService
from app.services.conversation_service import ConversationService
from app.services.cart_service import CartService
from app.services.ai_service import AIService, GeminiConfigError

class TestAIShoppingAssistant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Initialize SQLite database for grounding tests."""
        init_db()

    def setUp(self):
        """Clear conversation memory between tests."""
        ConversationService.clear_all()

    def _create_mock_client(self, structured_output: StructuredAIOutput):
        """Helper to create a mock google.genai Client returning structured JSON text."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = structured_output.model_dump_json()
        mock_client.models.generate_content.return_value = mock_response
        return mock_client

    def test_01_single_product_request(self):
        """Scenario 1: Customer requests one valid product."""
        mock_output = StructuredAIOutput(
            intent="add_to_cart",
            items=[ExtractedItem(product_query="Executive Hardcover Notebook", quantity=1, variant={"sizes": "A5"})],
            response_message="I found the Executive Hardcover Notebook in A5 size for you."
        )
        mock_client = self._create_mock_client(mock_output)

        resp = AIService.process_shopping_message(
            message="I need an A5 Executive Hardcover Notebook",
            session_id="test-s1",
            client_override=mock_client
        )

        self.assertEqual(len(resp.items), 1)
        item = resp.items[0]
        self.assertEqual(item.product_id, "prod_nb_exec")
        self.assertEqual(item.status, "available")
        self.assertEqual(item.quantity, 1)
        self.assertEqual(item.unit_price, 14.99)
        self.assertEqual(item.subtotal, 14.99)

    def test_02_multiple_product_request(self):
        """Scenario 2: Customer requests multiple products in a single prompt."""
        mock_output = StructuredAIOutput(
            intent="add_to_cart",
            items=[
                ExtractedItem(product_query="Executive Hardcover Notebook", quantity=2, variant={"sizes": "A5"}),
                ExtractedItem(product_query="Minimalist Gel Ink Pen Set", quantity=1, variant={"colors": "Blue"})
            ],
            response_message="I found two A5 notebooks and one blue pen set."
        )
        mock_client = self._create_mock_client(mock_output)

        resp = AIService.process_shopping_message(
            message="I need two A5 notebooks and one blue pen set",
            session_id="test-s2",
            client_override=mock_client
        )

        self.assertEqual(len(resp.items), 2)
        item1 = next(i for i in resp.items if i.product_id == "prod_nb_exec")
        item2 = next(i for i in resp.items if i.product_id == "prod_pen_gel")
        
        self.assertEqual(item1.quantity, 2)
        self.assertEqual(item1.unit_price, 14.99)
        self.assertEqual(item1.subtotal, 29.98)
        
        self.assertEqual(item2.quantity, 1)
        self.assertEqual(item2.unit_price, 9.99)
        self.assertEqual(item2.subtotal, 9.99)
        
        self.assertEqual(resp.estimated_total, 39.97)

    def test_03_quantity_extraction(self):
        """Scenario 3: Quantities in words correctly extracted and calculated."""
        mock_output = StructuredAIOutput(
            intent="add_to_cart",
            items=[ExtractedItem(product_query="Minimalist Gel Ink Pen Set", quantity=3, variant={"colors": "Black"})],
            response_message="Added three black pen sets."
        )
        mock_client = self._create_mock_client(mock_output)

        resp = AIService.process_shopping_message(
            message="Please get me three black pen sets",
            session_id="test-s3",
            client_override=mock_client
        )

        self.assertEqual(resp.items[0].quantity, 3)
        self.assertEqual(resp.items[0].subtotal, 29.97)
        self.assertEqual(resp.estimated_total, 29.97)

    def test_04_variant_extraction(self):
        """Scenario 4: Proper extraction and mapping of variant attributes."""
        mock_output = StructuredAIOutput(
            intent="add_to_cart",
            items=[ExtractedItem(product_query="Executive Hardcover Notebook", quantity=1, variant={"size": "A4", "color": "Emerald Green"})],
            response_message="Added A4 Emerald Green Notebook."
        )
        mock_client = self._create_mock_client(mock_output)

        resp = AIService.process_shopping_message(
            message="I want an Emerald Green A4 notebook",
            session_id="test-s4",
            client_override=mock_client
        )

        self.assertEqual(resp.items[0].variant.get("sizes"), "A4")
        self.assertEqual(resp.items[0].variant.get("colors"), "Emerald Green")

    def test_05_budget_extraction_and_alert(self):
        """Scenario 5: Budget extraction and threshold alerting."""
        mock_output = StructuredAIOutput(
            intent="add_to_cart",
            items=[
                ExtractedItem(product_query="Designing Data-Intensive Applications", quantity=2, variant={"formats": "Hardcover"})
            ],
            budget=50.0,
            response_message="Added two hardcovers."
        )
        mock_client = self._create_mock_client(mock_output)

        resp = AIService.process_shopping_message(
            message="I need two copies of DDIA, budget is $50",
            session_id="test-s5",
            client_override=mock_client
        )

        # 2 * 44.50 = $89.00, which exceeds $50.00
        self.assertEqual(resp.budget, 50.0)
        self.assertTrue(resp.budget_exceeded)
        self.assertIsNotNone(resp.budget_alert)
        self.assertIn("exceeds your stated budget", resp.budget_alert)

    def test_06_missing_product_in_catalogue(self):
        """Scenario 6: Handle customer requesting a product not sold in the store."""
        mock_output = StructuredAIOutput(
            intent="product_search",
            items=[ExtractedItem(product_query="Sony PlayStation 5 Console", quantity=1)],
            response_message="We do not carry gaming consoles."
        )
        mock_client = self._create_mock_client(mock_output)

        resp = AIService.process_shopping_message(
            message="Do you sell the PlayStation 5?",
            session_id="test-s6",
            client_override=mock_client
        )

        self.assertEqual(len(resp.items), 1)
        self.assertEqual(resp.items[0].status, "not_found")
        self.assertIn("not available in our store", resp.items[0].warning)

    def test_07_ambiguous_product_clarification(self):
        """Scenario 7: Ambiguous queries trigger clarification."""
        mock_output = StructuredAIOutput(
            intent="product_search",
            items=[ExtractedItem(product_query="book", quantity=1)],
            response_message="I found several books in our catalogue."
        )
        mock_client = self._create_mock_client(mock_output)

        resp = AIService.process_shopping_message(
            message="I want to buy a book",
            session_id="test-s7",
            client_override=mock_client
        )

        self.assertTrue(resp.clarification_needed)
        self.assertIsNotNone(resp.clarification_question)
        self.assertIn("Did you mean", resp.clarification_question)

    def test_08_unavailable_variant(self):
        """Scenario 8: Customer requests an invalid variant (e.g. A3 size)."""
        mock_output = StructuredAIOutput(
            intent="add_to_cart",
            items=[ExtractedItem(product_query="Executive Hardcover Notebook", quantity=1, variant={"sizes": "A3"})],
            response_message="Looking for A3 notebook."
        )
        mock_client = self._create_mock_client(mock_output)

        resp = AIService.process_shopping_message(
            message="I need an A3 size notebook",
            session_id="test-s8",
            client_override=mock_client
        )

        self.assertEqual(resp.items[0].status, "variant_unavailable")
        self.assertIn("not valid for sizes", resp.items[0].warning)

    def test_09_insufficient_stock(self):
        """Scenario 9: Customer requests quantity exceeding inventory."""
        mock_output = StructuredAIOutput(
            intent="add_to_cart",
            items=[ExtractedItem(product_query="Ergonomic Aluminum Laptop Stand", quantity=500)],
            response_message="Checking 500 stands."
        )
        mock_client = self._create_mock_client(mock_output)

        resp = AIService.process_shopping_message(
            message="I want 500 laptop stands",
            session_id="test-s9",
            client_override=mock_client
        )

        self.assertEqual(resp.items[0].status, "insufficient_stock")
        self.assertIn("Only", resp.items[0].warning)
        self.assertIn("available in stock", resp.items[0].warning)

    def test_10_follow_up_clarification(self):
        """Scenario 10: Multi-turn conversational clarification and resolution."""
        # Turn 1: User says "I need notebooks" (missing size)
        mock_output_turn1 = StructuredAIOutput(
            intent="clarification",
            items=[ExtractedItem(product_query="Executive Hardcover Notebook", quantity=2)],
            clarification_needed=True,
            clarification_question="For Executive Hardcover Notebook, what size would you prefer: A4 or A5?",
            response_message="Would you prefer A4 or A5?"
        )
        mock_client1 = self._create_mock_client(mock_output_turn1)

        resp1 = AIService.process_shopping_message(
            message="I need two notebooks",
            session_id="test-s10",
            client_override=mock_client1
        )
        self.assertTrue(resp1.clarification_needed)

        # Turn 2: User answers "A5"
        resp2 = AIService.process_shopping_message(
            message="A5",
            session_id="test-s10"
        )
        self.assertFalse(resp2.clarification_needed)
        self.assertEqual(resp2.items[0].product_id, "prod_nb_exec")
        self.assertEqual(resp2.items[0].variant.get("sizes"), "A5")

    def test_11_conversation_context_isolation(self):
        """Scenario 11: Context from session A does not leak into session B."""
        ConversationService.update_context("session-A", product_id="prod_nb_exec")
        ConversationService.update_context("session-B", product_id="prod_pen_gel")

        ctx_a = ConversationService.get_context("session-A")
        ctx_b = ConversationService.get_context("session-B")

        self.assertEqual(ctx_a["last_discussed_product_id"], "prod_nb_exec")
        self.assertEqual(ctx_b["last_discussed_product_id"], "prod_pen_gel")
        self.assertNotEqual(ctx_a["last_discussed_product_id"], ctx_b["last_discussed_product_id"])

    def test_12_invalid_ai_response_handling(self):
        """Scenario 12: Graceful handling of malformed JSON from LLM."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "{ malformed json: not valid ... }"
        mock_client.models.generate_content.return_value = mock_response

        # AIService.call_gemini should not crash with unhandled exception
        result = AIService.call_gemini(
            message="gibberish test",
            session_id="test-s12",
            client_override=mock_client
        )
        self.assertTrue(result.clarification_needed)
        self.assertEqual(result.intent, "clarification")

    def test_13_missing_gemini_api_key(self):
        """Scenario 13: Explicit error raised if Gemini API key is missing."""
        with patch.object(settings, "GEMINI_API_KEY", ""):
            with self.assertRaises(GeminiConfigError) as ctx:
                AIService.get_gemini_client()
            self.assertIn("GEMINI_API_KEY is not configured", str(ctx.exception))
            self.assertIn("https://aistudio.google.com/", str(ctx.exception))

    def test_14_catalogue_price_grounding(self):
        """Scenario 14: Backend prices are authoritative regardless of LLM assertions."""
        # Suppose model returned an arbitrary hallucinated price in response
        mock_output = StructuredAIOutput(
            intent="add_to_cart",
            items=[ExtractedItem(product_query="Executive Hardcover Notebook", quantity=2, variant={"sizes": "A5"})],
            response_message="I found it for $1.00 each!"
        )
        mock_client = self._create_mock_client(mock_output)

        resp = AIService.process_shopping_message(
            message="Get me two A5 notebooks",
            session_id="test-s14",
            client_override=mock_client
        )

        # Grounded price must be the DB price $14.99, NOT hallucinated $1.00
        self.assertEqual(resp.items[0].unit_price, 14.99)
        self.assertEqual(resp.items[0].subtotal, 29.98)
        self.assertEqual(resp.estimated_total, 29.98)

    def test_15_checkout_intent_with_empty_cart(self):
        """Scenario 15: Checkout intent with empty cart informs user to add products first."""
        session_id = "test-empty-checkout"
        CartService.clear_cart(session_id)

        resp = AIService.process_shopping_message(
            message="checkout",
            session_id=session_id
        )

        self.assertEqual(resp.intent, "checkout")
        self.assertIn("empty", resp.message.lower())
        self.assertEqual(len(resp.items), 0)

    def test_16_checkout_intent_with_items_in_cart(self):
        """Scenario 16: Checkout intent with items guides user to PayPal and preserves cart."""
        session_id = "test-items-checkout"
        CartService.clear_cart(session_id)
        CartService.add_item(session_id, "prod_nb_exec", quantity=2, selected_variants={"sizes": "A5"})

        resp = AIService.process_shopping_message(
            message="proceed to payment",
            session_id=session_id
        )

        self.assertEqual(resp.intent, "checkout")
        self.assertIn("paypal", resp.message.lower())
        self.assertIn("29.98", resp.message)
        # Verify cart items were preserved in SQLite
        cart = CartService.get_cart(session_id)
        self.assertEqual(len(cart["items"]), 1)
        self.assertEqual(cart["subtotal"], 29.98)

if __name__ == "__main__":
    unittest.main()

