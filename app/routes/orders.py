from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Query
from app.schemas.order import OrderResponse, OrderListResponse
from app.services.order_service import OrderService

router = APIRouter(prefix="/api/orders", tags=["Orders"])

@router.get("", response_model=OrderListResponse)
def get_all_orders(limit: int = Query(50, ge=1, le=200)):
    """Retrieve recent orders for merchant administration and order tracking."""
    orders = OrderService.get_all_orders(limit=limit)
    return OrderListResponse(
        total=len(orders),
        orders=[OrderResponse(**o) for o in orders]
    )

@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: str):
    """Retrieve full details for an order by internal order ID or PayPal Order ID."""
    order = OrderService.get_order(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID '{order_id}' was not found."
        )
    return OrderResponse(**order)

@router.get("/session/{session_id}", response_model=List[OrderResponse])
def get_orders_by_session(session_id: str):
    """Retrieve all orders placed under a specific customer session."""
    orders = OrderService.get_orders_by_session(session_id)
    return [OrderResponse(**o) for o in orders]

