from typing import Optional
from pydantic import BaseModel, Field

class CreateOrderRequest(BaseModel):
    session_id: str = Field(..., description="Active cart session ID")
    customer_name: Optional[str] = Field(default=None, description="Customer full name")
    customer_email: Optional[str] = Field(default=None, description="Customer email address")

class CreateOrderResponse(BaseModel):
    order_id: str = Field(description="Internal system order ID")
    paypal_order_id: str = Field(description="PayPal v2 Order ID for client SDK")
    total_amount: float
    currency: str = "USD"
    status: str = "PENDING"

class CaptureOrderRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, description="Session ID for additional ownership validation")

class CaptureOrderResponse(BaseModel):
    order_id: str
    paypal_order_id: str
    capture_id: Optional[str] = None
    status: str
    amount_captured: float
    currency: str = "USD"
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    message: str

class CancelOrderResponse(BaseModel):
    order_id: str
    paypal_order_id: str
    status: str = "CANCELLED"
    message: str

class CheckoutConfigResponse(BaseModel):
    client_id: str
    currency: str = "USD"
    mode: str = "sandbox"

