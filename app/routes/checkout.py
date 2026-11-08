from typing import Optional
from fastapi import APIRouter, HTTPException, status
from app.config import settings
from app.schemas.checkout import (
    CreateOrderRequest,
    CreateOrderResponse,
    CaptureOrderRequest,
    CaptureOrderResponse,
    CancelOrderResponse,
    CheckoutConfigResponse
)
from app.services.order_service import OrderService
from app.services.paypal_service import PayPalConfigError, PayPalAPIError

router = APIRouter(prefix="/api/checkout", tags=["Checkout"])

@router.get("/config", response_model=CheckoutConfigResponse)
def get_checkout_config():
    """
    Provide public PayPal configuration to the frontend for loading the PayPal JS SDK.
    Never exposes the PayPal client secret!
    """
    return CheckoutConfigResponse(
        client_id=settings.PAYPAL_CLIENT_ID or "sb",
        currency=settings.PAYPAL_CURRENCY,
        mode=settings.PAYPAL_MODE
    )

@router.post("/create-order", response_model=CreateOrderResponse, status_code=status.HTTP_201_CREATED)
def create_checkout_order(request: CreateOrderRequest):
    """
    Initiate checkout: validates persistent cart, rechecks stock and prices,
    creates a PayPal v2 order, and saves a draft order record in SQLite.
    """
    try:
        order_info = OrderService.create_order_from_cart(
            session_id=request.session_id,
            customer_name=request.customer_name,
            customer_email=request.customer_email
        )
        return CreateOrderResponse(**order_info)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke).strip("'\""))
    except PayPalConfigError as pce:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(pce))
    except PayPalAPIError as pae:
        raise HTTPException(status_code=pae.status_code, detail=str(pae))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create PayPal order: {str(e)}"
        )

@router.post("/capture-order/{order_id}", response_model=CaptureOrderResponse, status_code=status.HTTP_200_OK)
def capture_checkout_order(order_id: str, request: Optional[CaptureOrderRequest] = None):
    """
    Capture approved PayPal payment, verify amount & currency, deduct inventory,
    mark order COMPLETED, and clear the session cart.
    Idempotent: safe against repeated clicks or network retries.
    """
    session_id = request.session_id if request else None
    try:
        capture_result = OrderService.capture_and_finalize_order(
            order_identifier=order_id,
            session_id=session_id
        )
        return CaptureOrderResponse(**capture_result)
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke).strip("'\""))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except PayPalConfigError as pce:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(pce))
    except PayPalAPIError as pae:
        raise HTTPException(status_code=pae.status_code, detail=str(pae))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to capture order: {str(e)}"
        )

@router.post("/cancel-order/{order_id}", response_model=CancelOrderResponse, status_code=status.HTTP_200_OK)
def cancel_checkout_order(order_id: str):
    """
    Mark order as CANCELLED when customer cancels during PayPal approval modal.
    Does not deduct inventory or delete the customer's cart.
    """
    try:
        result = OrderService.cancel_order(order_identifier=order_id)
        return CancelOrderResponse(**result)
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke).strip("'\""))
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel order: {str(e)}"
        )
