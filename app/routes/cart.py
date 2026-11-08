from fastapi import APIRouter, HTTPException, status
from app.schemas.cart import (
    AddToCartItemRequest,
    UpdateCartItemRequest,
    CartResponse
)
from app.services.cart_service import CartService

router = APIRouter(prefix="/api/cart", tags=["Cart"])

@router.get("/{session_id}", response_model=CartResponse, status_code=status.HTTP_200_OK)
def get_cart(session_id: str):
    """
    Retrieve the persistent shopping cart for a given session.
    Calculates authoritative subtotals and checks budget constraints.
    """
    try:
        cart = CartService.get_cart(session_id)
        return CartResponse(**cart)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve cart: {str(e)}"
        )

@router.post("/{session_id}/items", response_model=CartResponse, status_code=status.HTTP_201_CREATED)
def add_item_to_cart(session_id: str, request: AddToCartItemRequest):
    """
    Add a product to the session cart.
    Validates product ID, selected variants, and live stock against the catalogue.
    Recalculates backend totals using authoritative database prices.
    """
    try:
        updated_cart = CartService.add_item(
            session_id=session_id,
            product_id=request.product_id,
            quantity=request.quantity,
            selected_variants=request.selected_variants
        )
        return CartResponse(**updated_cart)
    except KeyError as ke:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(ke).strip("'\"")
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add item to cart: {str(e)}"
        )

@router.patch("/{session_id}/items/{item_id}", response_model=CartResponse, status_code=status.HTTP_200_OK)
def update_cart_item(session_id: str, item_id: str, request: UpdateCartItemRequest):
    """
    Update quantity or selected variants for an existing item in the cart.
    Validates stock availability and rejects zero/negative quantities.
    """
    try:
        updated_cart = CartService.update_item(
            session_id=session_id,
            item_id=item_id,
            quantity=request.quantity,
            selected_variants=request.selected_variants
        )
        return CartResponse(**updated_cart)
    except KeyError as ke:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(ke).strip("'\"")
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update cart item: {str(e)}"
        )

@router.delete("/{session_id}/items/{item_id}", response_model=CartResponse, status_code=status.HTTP_200_OK)
def remove_cart_item(session_id: str, item_id: str):
    """
    Remove an individual item from the session's active cart.
    Automatically recalculates cart totals.
    """
    try:
        updated_cart = CartService.remove_item(session_id=session_id, item_id=item_id)
        return CartResponse(**updated_cart)
    except KeyError as ke:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(ke).strip("'\"")
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove item: {str(e)}"
        )

@router.delete("/{session_id}", response_model=CartResponse, status_code=status.HTTP_200_OK)
def clear_cart(session_id: str):
    """
    Remove all items from the session's active cart.
    """
    try:
        cleared_cart = CartService.clear_cart(session_id=session_id)
        return CartResponse(**cleared_cart)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear cart: {str(e)}"
        )

