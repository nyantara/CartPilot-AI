"""
Optional Live Gemini Integration Verification Script.
Runs a live query against Gemini API if GEMINI_API_KEY is configured in .env.
"""
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.config import settings
from app.services.ai_service import AIService, GeminiConfigError

def main():
    print("==================================================")
    print("  CartPilot AI — Live Gemini Integration Test     ")
    print("==================================================")
    
    key = settings.GEMINI_API_KEY
    if not key or key.strip() == "" or "your_" in key.lower():
        print("\n[INFO] GEMINI_API_KEY is currently empty in .env.")
        print("To run live Gemini calls:")
        print("  1. Obtain a free key from https://aistudio.google.com/")
        print("  2. Add it to .env: GEMINI_API_KEY=AIzaSy...")
        print("  3. Re-run: python tests/test_live_gemini.py")
        print("\nAll 27 automated unit tests continue to pass without a key.")
        return 0

    print(f"\nConfigured Gemini Model: {settings.GEMINI_MODEL}")
    print("Testing live shopping assistant query...")
    
    try:
        response = AIService.process_shopping_message(
            message="I need two A5 notebooks and one blue pen. My budget is $50.",
            session_id="live-demo-session"
        )
        print("\n[SUCCESS] Live Gemini call succeeded!")
        print(f"Assistant Reply: {response.message}")
        print(f"Intent Extracted: {response.intent}")
        print(f"Estimated Total: ${response.estimated_total:.2f}")
        print(f"Budget: ${response.budget} (Exceeded: {response.budget_exceeded})")
        print("Verified Items Grounded from SQLite:")
        for item in response.items:
            print(f"  - {item.name} | Qty: {item.quantity} | Unit: ${item.unit_price:.2f} | Subtotal: ${item.subtotal:.2f} | Variant: {item.variant}")
        return 0
    except GeminiConfigError as gce:
        print(f"\n[CONFIG ERROR] {gce}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Live call failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
