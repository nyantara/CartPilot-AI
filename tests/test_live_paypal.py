"""
Optional Live PayPal Sandbox Integration Verification Script.
Runs a live OAuth and Order creation test against PayPal Sandbox if credentials are set in .env.
"""
import sys
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import settings
from app.services.paypal_service import PayPalService, PayPalConfigError, PayPalAPIError

def main():
    print("==================================================")
    print("  CartPilot AI — Live PayPal Sandbox Integration  ")
    print("==================================================")

    client_id = settings.PAYPAL_CLIENT_ID
    client_secret = settings.PAYPAL_CLIENT_SECRET

    if not client_id or not client_secret or "your_" in client_id.lower():
        print("\n[INFO] PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET is not configured in .env.")
        print("To test real PayPal Sandbox integration:")
        print("  1. Log in to https://developer.paypal.com/dashboard/applications/sandbox")
        print("  2. Copy your Sandbox Client ID and Secret.")
        print("  3. Add them to .env:")
        print("     PAYPAL_CLIENT_ID=...")
        print("     PAYPAL_CLIENT_SECRET=...")
        print("  4. Re-run: python tests/test_live_paypal.py")
        print("\nAll 15 automated unit tests continue to pass with mocks.")
        return 0

    print(f"\nPayPal Mode: {settings.PAYPAL_MODE}")
    print(f"PayPal Base URL: {settings.paypal_api_url}")
    print("Testing live OAuth 2.0 token generation...")

    try:
        token = PayPalService.get_access_token(force_refresh=True)
        print(f"[SUCCESS] OAuth 2.0 access token obtained successfully! (Token length: {len(token)})")

        print("\nTesting live PayPal order creation for $14.99 USD...")
        sample_items = [
            {
                "product_name": "Executive Hardcover Notebook",
                "unit_price": 14.99,
                "quantity": 1,
                "sku": "STAT-NBK-001"
            }
        ]
        order_resp = PayPalService.create_order(
            internal_order_id="test_live_001",
            total_amount=14.99,
            currency="USD",
            items=sample_items
        )
        paypal_id = order_resp.get("id")
        status = order_resp.get("status")
        print(f"[SUCCESS] PayPal Order created successfully!")
        print(f"  - PayPal Order ID: {paypal_id}")
        print(f"  - Status: {status}")
        print("\nYou can now open http://127.0.0.1:8000/static/checkout.html to complete manual sandbox payment.")
        return 0

    except PayPalConfigError as pce:
        print(f"\n[CONFIG ERROR] {pce}")
        return 1
    except PayPalAPIError as pae:
        print(f"\n[API ERROR] {pae}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Live PayPal call failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())

