from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class ProductBase(BaseModel):
    id: str
    name: str
    description: str
    category: str
    price: float
    stock: int
    variants: Dict[str, List[str]] = Field(default_factory=dict)
    image_url: str
    sku: str

class ProductResponse(ProductBase):
    created_at: Optional[str] = None

class ProductListResponse(BaseModel):
    total: int
    products: List[ProductResponse]

