import time
import logging
import requests
from typing import Dict, List, Optional, Any
from app.config import settings

logger = logging.getLogger(__name__)

class PayPalConfigError(Exception):
    """Raised when PayPal Sandbox credentials are not properly configured."""
    pass

class PayPalAPIError(Exception):
    """Raised when a PayPal API request fails."""
    def __init__(self, message: str, status_code: int = 400, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details

class PayPalService:
    _access_token: Optional[str] = None
    _token_expires_at: float = 0.0

    @classmethod
    def get_access_token(cls, force_refresh: bool = False) -> str:
        """
        Obtain OAuth 2.0 access token from PayPal using client credentials.
        Caches the token in-memory until expiration.
        """
        client_id = settings.PAYPAL_CLIENT_ID
        client_secret = settings.PAYPAL_CLIENT_SECRET
        
        if not client_id or not client_secret or "your_" in client_id.lower() or "your_" in client_secret.lower():
            raise PayPalConfigError(
                "PayPal credentials not configured. Please set PAYPAL_CLIENT_ID and "
                "PAYPAL_CLIENT_SECRET in your .env file from your PayPal Developer Sandbox account."
            )

        # Return cached token if valid (with 60-second buffer)
        if not force_refresh and cls._access_token and time.time() < (cls._token_expires_at - 60):
            return cls._access_token

        url = f"{settings.paypal_api_url}/v1/oauth2/token"
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en_US"
        }
        data = {"grant_type": "client_credentials"}

        try:
            response = requests.post(
                url,
                auth=(client_id, client_secret),
                headers=headers,
                data=data,
                timeout=12.0
            )
            
            if response.status_code != 200:
                logger.error(f"PayPal OAuth failed [{response.status_code}]: {response.text}")
                raise PayPalAPIError(
                    f"PayPal OAuth authentication failed: {response.text}",
                    status_code=response.status_code
                )
                
            res_json = response.json()
            cls._access_token = res_json["access_token"]
            expires_in = res_json.get("expires_in", 32400) # default 9 hours
            cls._token_expires_at = time.time() + float(expires_in)
            return cls._access_token
            
        except requests.RequestException as re:
            logger.error(f"Network error communicating with PayPal OAuth: {re}")
            raise PayPalAPIError(f"Network error during PayPal authentication: {str(re)}", status_code=503)

    @classmethod
    def create_order(
        cls,
        internal_order_id: str,
        total_amount: float,
        currency: str,
        items: List[Dict[str, Any]],
        custom_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a PayPal order via Orders API v2 (intent=CAPTURE).
        Authoritative line items and total amounts are sent to PayPal.
        """
        token = cls.get_access_token()
        url = f"{settings.paypal_api_url}/v2/checkout/orders"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "Prefer": "return=representation"
        }

        # Format items breakdown ensuring exact sum equality
        paypal_items = []
        calculated_item_total = 0.0
        for item in items:
            unit_price = round(float(item["unit_price"]), 2)
            qty = int(item["quantity"])
            subtotal = round(unit_price * qty, 2)
            calculated_item_total += subtotal
            
            name = item.get("product_name", "Cart Item")
            if item.get("variant_details"):
                var_str = ", ".join(f"{k}: {v}" for k, v in item["variant_details"].items())
                name = f"{name} ({var_str})"

            paypal_items.append({
                "name": name[:127],
                "quantity": str(qty),
                "unit_amount": {
                    "currency_code": currency,
                    "value": f"{unit_price:.2f}"
                },
                "sku": str(item.get("sku", item.get("product_id", "")))[:127],
                "category": "PHYSICAL_GOODS"
            })

        calculated_item_total = round(calculated_item_total, 2)
        total_str = f"{total_amount:.2f}"

        # Standard callback URLs for web/SDK fallback
        return_url = "http://127.0.0.1:8000/static/checkout.html?payment=success"
        cancel_url = "http://127.0.0.1:8000/static/checkout.html?payment=cancelled"

        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": internal_order_id,
                    "description": f"CartPilot AI Order {internal_order_id}",
                    "custom_id": (custom_id or internal_order_id)[:127],
                    "amount": {
                        "currency_code": currency,
                        "value": total_str,
                        "breakdown": {
                            "item_total": {
                                "currency_code": currency,
                                "value": f"{calculated_item_total:.2f}"
                            }
                        }
                    },
                    "items": paypal_items
                }
            ],
            "payment_source": {
                "paypal": {
                    "experience_context": {
                        "payment_method_preference": "IMMEDIATE_PAYMENT_REQUIRED",
                        "brand_name": "CartPilot AI",
                        "locale": "en-US",
                        "landing_page": "LOGIN",
                        "shipping_preference": "NO_SHIPPING",
                        "user_action": "PAY_NOW",
                        "return_url": return_url,
                        "cancel_url": cancel_url
                    }
                }
            }
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15.0)
            if response.status_code not in (200, 201):
                logger.error(f"PayPal create order failed [{response.status_code}]: {response.text}")
                raise PayPalAPIError(
                    f"PayPal order creation failed: {response.text}",
                    status_code=response.status_code,
                    details=response.text
                )
            return response.json()
        except requests.RequestException as re:
            logger.error(f"Network error during PayPal create order: {re}")
            raise PayPalAPIError(f"Network error communicating with PayPal: {str(re)}", status_code=503)

    @classmethod
    def capture_order(cls, paypal_order_id: str) -> Dict[str, Any]:
        """
        Capture payment for an approved PayPal order.
        Uses idempotency header to prevent accidental double-captures.
        """
        token = cls.get_access_token()
        url = f"{settings.paypal_api_url}/v2/checkout/orders/{paypal_order_id}/capture"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "Prefer": "return=representation",
            "PayPal-Request-Id": f"capture_{paypal_order_id}"
        }

        try:
            response = requests.post(url, headers=headers, json={}, timeout=20.0)
            if response.status_code not in (200, 201):
                logger.error(f"PayPal capture order failed [{response.status_code}]: {response.text}")
                raise PayPalAPIError(
                    f"PayPal payment capture failed: {response.text}",
                    status_code=response.status_code,
                    details=response.text
                )
            return response.json()
        except requests.RequestException as re:
            logger.error(f"Network error during PayPal capture: {re}")
            raise PayPalAPIError(f"Network error communicating with PayPal: {str(re)}", status_code=503)

    @classmethod
    def get_order_details(cls, paypal_order_id: str) -> Dict[str, Any]:
        """Fetch order status and details directly from PayPal Orders API."""
        token = cls.get_access_token()
        url = f"{settings.paypal_api_url}/v2/checkout/orders/{paypal_order_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        try:
            response = requests.get(url, headers=headers, timeout=12.0)
            if response.status_code != 200:
                raise PayPalAPIError(
                    f"Failed to fetch PayPal order details: {response.text}",
                    status_code=response.status_code
                )
            return response.json()
        except requests.RequestException as re:
            raise PayPalAPIError(f"Network error: {str(re)}", status_code=503)

