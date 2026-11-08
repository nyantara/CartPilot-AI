from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class AddToCartItemRequest(BaseModel):
    product_id: str = Field(..., description="ID of the product to add")
    quantity: int = Field(default=1, gt=0, description="Quantity to add (must be > 0)")
    selected_variants: Dict[str, str] = Field(default_factory=dict, description="Selected variants, e.g. {'sizes': 'A5'}")

class UpdateCartItemRequest(BaseModel):
    quantity: Optional[int] = Field(default=None, gt=0, description="Updated quantity (must be > 0)")
    selected_variants: Optional[Dict[str, str]] = Field(default=None, description="Updated variant choices")

class CartItemDetail(BaseModel):
    id: str = Field(description="Unique cart item identifier")
    cart_id: str = Field(description="Foreign key to the parent cart")
    product_id: str
    product_name: str
    category: str
    quantity: int
    selected_variants: Dict[str, str] = Field(default_factory=dict)
    unit_price: float
    subtotal: float
    image_url: str
    sku: str
    stock_available: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class CartResponse(BaseModel):
    id: str = Field(description="Unique cart ID")
    session_id: str = Field(description="Session ID associated with this cart")
    status: str = Field(default="ACTIVE", description="Cart status: ACTIVE, CHECKED_OUT, ABANDONED")
    items: List[CartItemDetail] = Field(default_factory=list)
    total_items: int = 0
    subtotal: float = 0.0
    currency: str = "USD"
    budget: Optional[float] = None
    budget_exceeded: bool = False
    budget_alert: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

# Aliases for compatibility
CartSummary = CartResponse
CartItem = CartItemDetail
