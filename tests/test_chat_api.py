import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from app.database.db import init_db
from app.config import settings
from app.schemas.chat import ChatRequest, StructuredAIOutput, ExtractedItem
from app.routes.chat import handle_chat_message
from app.services.conversation_service import ConversationService
from app.services.ai_service import AIService

class TestChatAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        ConversationService.clear_all()

    def test_empty_message_raises_400(self):
        """Test that submitting an empty message raises 400 Bad Request."""
        with self.assertRaises(HTTPException) as ctx:
            handle_chat_message(ChatRequest(session_id="api-test", message="   "))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_missing_api_key_returns_503(self):
        """Test that missing GEMINI_API_KEY returns 503 with guidance."""
        with patch.object(settings, "GEMINI_API_KEY", ""):
            with self.assertRaises(HTTPException) as ctx:
                handle_chat_message(ChatRequest(session_id="api-test", message="I need a notebook"))
            self.assertEqual(ctx.exception.status_code, 503)
            self.assertIn("GEMINI_API_KEY is not configured", ctx.exception.detail)

    def test_successful_chat_request_with_grounded_response(self):
        """Test full chat pipeline through route handler."""
        mock_output = StructuredAIOutput(
            intent="add_to_cart",
            items=[ExtractedItem(product_query="Executive Hardcover Notebook", quantity=1, variant={"sizes": "A5"})],
            response_message="I found the A5 notebook for you."
        )
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = mock_output.model_dump_json()
        mock_client.models.generate_content.return_value = mock_resp

        with patch.object(AIService, "get_gemini_client", return_value=mock_client):
            response = handle_chat_message(ChatRequest(session_id="session-route-1", message="I need an A5 notebook"))
            self.assertEqual(response.session_id, "session-route-1")
            self.assertEqual(response.intent, "add_to_cart")
            self.assertEqual(len(response.items), 1)
            self.assertEqual(response.items[0].product_id, "prod_nb_exec")
            self.assertEqual(response.items[0].unit_price, 14.99)
            self.assertEqual(response.estimated_total, 14.99)

if __name__ == "__main__":
    unittest.main()

