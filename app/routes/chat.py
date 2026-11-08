from fastapi import APIRouter, HTTPException, status
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.ai_service import AIService, GeminiConfigError

router = APIRouter(prefix="/api/chat", tags=["Chat"])

@router.post("", response_model=ChatResponse, status_code=status.HTTP_200_OK)
def handle_chat_message(request: ChatRequest):
    """
    Process natural-language shopping messages through Gemini AI,
    ground all product intents strictly against the SQLite catalogue,
    validate stock, variants, and prices, and return verified shopping intentions.
    """
    if not request.message or not request.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty."
        )

    try:
        response = AIService.process_shopping_message(
            message=request.message,
            session_id=request.session_id
        )
        return response
    except GeminiConfigError as gce:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(gce)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while processing the shopping assistant request: {str(e)}"
        )

