from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from app.schemas.cart import CartResponse

class ItemVariant(BaseModel):
    name: str = Field(description="Variant name such as 'size', 'color', 'format'")
    value: str = Field(description="Variant value such as 'A5', 'Blue', 'Hardcover'")

class ExtractedItem(BaseModel):
    """Raw product intent extracted by AI."""
    product_query: str = Field(description="Name or description of the product requested by the customer")
    quantity: int = Field(default=1, ge=1, description="Quantity requested, defaults to 1")
    variants: List[ItemVariant] = Field(default_factory=list, description="Requested variant options")
    action: str = Field(default="add", description="Action type: add, remove, or update")

    def __init__(self, **data):
        # Support passing variant={"sizes": "A5"} backwards-compatibly
        if "variant" in data and "variants" not in data:
            raw_v = data.pop("variant")
            if isinstance(raw_v, dict):
                data["variants"] = [ItemVariant(name=k, value=str(v)) for k, v in raw_v.items()]
            elif isinstance(raw_v, list):
                data["variants"] = raw_v
        super().__init__(**data)

    @property
    def variant(self) -> Dict[str, str]:
        """Backwards-compatible dict representation of selected variants."""
        return {v.name: v.value for v in self.variants}

class StructuredAIOutput(BaseModel):
    """Structured JSON schema that the Gemini model must strictly generate."""
    intent: str = Field(
        default="add_to_cart",
        description="One of: add_to_cart, modify_cart, remove_from_cart, product_search, product_recommendation, general_question, clarification, checkout"
    )
    items: List[ExtractedItem] = Field(default_factory=list, description="Extracted product requests")
    budget: Optional[float] = Field(default=None, description="Customer stated budget in monetary units, if mentioned")
    clarification_needed: bool = Field(default=False, description="True if customer request is missing key info or ambiguous")
    clarification_question: Optional[str] = Field(default=None, description="Question to ask the customer if clarification needed")
    response_message: str = Field(description="Conversational, friendly response message to the customer")
    suggestions: List[str] = Field(default_factory=list, description="2-4 helpful quick-reply suggestions for the user")

class ChatRequest(BaseModel):
    """Client request schema for POST /api/chat."""
    session_id: str = Field(default="default-session", description="Unique conversation session ID")
    message: str = Field(..., min_length=1, max_length=1000, description="Customer input text")

class VerifiedProductItem(BaseModel):
    """Grounded product item verified strictly against the SQLite catalogue."""
    product_id: str
    name: str
    category: str
    unit_price: float
    quantity: int
    variant: Dict[str, str] = Field(default_factory=dict)
    subtotal: float
    stock_available: int
    image_url: str
    sku: str
    status: str = Field(default="available", description="available, insufficient_stock, variant_unavailable, or ambiguous")
    warning: Optional[str] = None

class ChatResponse(BaseModel):
    """API response schema returned by POST /api/chat."""
    session_id: str
    message: str
    intent: str
    items: List[VerifiedProductItem] = Field(default_factory=list)
    clarification_needed: bool = False
    clarification_question: Optional[str] = None
    budget: Optional[float] = None
    budget_exceeded: bool = False
    budget_alert: Optional[str] = None
    estimated_total: float = 0.0
    suggestions: List[str] = Field(default_factory=list)
    cart: Optional[CartResponse] = None
