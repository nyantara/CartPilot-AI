from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from app.schemas.product import ProductResponse, ProductListResponse
from app.services.catalogue_service import CatalogueService

router = APIRouter(prefix="/api/products", tags=["Products"])

@router.get("", response_model=ProductListResponse)
def get_products(
    category: Optional[str] = Query(None, description="Filter products by category name"),
    search: Optional[str] = Query(None, description="Search term for product name or description")
):
    """Retrieve all products in the catalogue, with optional category filtering and search."""
    products = CatalogueService.get_all_products(category=category, search=search)
    return ProductListResponse(
        total=len(products),
        products=[ProductResponse(**p) for p in products]
    )

@router.get("/categories", response_model=List[str])
def get_categories():
    """Retrieve all available product categories."""
    return CatalogueService.get_categories()

@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: str):
    """Retrieve detailed information for a single product by its ID."""
    product = CatalogueService.get_product_by_id(product_id)
    if not product:
        raise HTTPException(
            status_code=404,
            detail=f"Product with ID '{product_id}' was not found in the catalogue."
        )
    return ProductResponse(**product)

