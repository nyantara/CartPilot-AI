from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from app.schemas.order import OrderResponse

class LowStockProduct(BaseModel):
    id: str
    name: str
    category: str
    stock: int
    sku: str

class DashboardSummaryResponse(BaseModel):
    total_orders: int = Field(default=0, description="Total number of orders created")
    successful_payments: int = Field(default=0, description="Orders with COMPLETED payment")
    pending_payments: int = Field(default=0, description="Orders with PENDING payment")
    failed_payments: int = Field(default=0, description="Orders with FAILED payment")
    cancelled_payments: int = Field(default=0, description="Orders with CANCELLED payment")
    total_sales: float = Field(default=0.0, description="Total gross sales from COMPLETED orders")
    currency: str = Field(default="USD", description="Default currency code")
    recent_orders: List[OrderResponse] = Field(default_factory=list, description="Latest orders with line items")
    total_products: int = Field(default=0, description="Total product catalogue count")
    low_stock_alerts: List[LowStockProduct] = Field(default_factory=list, description="Products requiring restocking")

