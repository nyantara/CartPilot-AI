from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class OrderItemDetail(BaseModel):
    id: Optional[int] = None
    order_id: str
    product_id: str
    product_name: str
    variant_details: Dict[str, str] = Field(default_factory=dict)
    quantity: int
    unit_price: float
    subtotal: float

class OrderResponse(BaseModel):
    id: str = Field(description="Internal unique order ID")
    session_id: Optional[str] = None
    paypal_order_id: Optional[str] = None
    paypal_capture_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    total_amount: float
    currency: str = "USD"
    payment_status: str = Field(description="CREATED, COMPLETED, FAILED, or CANCELLED")
    items: List[OrderItemDetail] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class OrderListResponse(BaseModel):
    total: int
    orders: List[OrderResponse]

