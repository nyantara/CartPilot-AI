import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from pydantic import ValidationError

from app.config import settings
from app.schemas.chat import (
    ExtractedItem,
    StructuredAIOutput,
    VerifiedProductItem,
    ChatResponse
)
from app.schemas.cart import CartResponse
from app.services.catalogue_service import CatalogueService
from app.services.conversation_service import ConversationService
from app.services.cart_service import CartService

logger = logging.getLogger(__name__)

class GeminiConfigError(Exception):
    """Raised when the Gemini API is not configured properly."""
    pass

class AIService:
    @classmethod
    def get_gemini_client(cls, api_key: Optional[str] = None):
        """
        Instantiate the official Google Gen AI SDK client.
        Raises GeminiConfigError if key is not configured.
        """
        key = api_key or settings.GEMINI_API_KEY
        if not key or key.strip() == "" or "your_" in key.lower():
            raise GeminiConfigError(
                "GEMINI_API_KEY is not configured. Please add your GEMINI_API_KEY to your .env file "
                "or export it as an environment variable. Get a free key at https://aistudio.google.com/"
            )
        try:
            from google import genai
            return genai.Client(api_key=key)
        except Exception as e:
            raise GeminiConfigError(f"Failed to initialize Google Gen AI client: {str(e)}")

    @classmethod
    def generate_system_instruction(cls) -> str:
        """Construct the grounding system instruction with full catalogue context."""
        catalogue_text = CatalogueService.get_catalogue_summary_for_ai()
        return f"""You are CartPilot AI, an expert, friendly, and precise shopping assistant for an online store.
Your goal is to understand customer shopping requests and output STRICT structured JSON.

STORE PRODUCT CATALOGUE (Ground Truth - ONLY these products exist in the store):
{catalogue_text}

CRITICAL RULES:
1. NEVER invent products, prices, variants, or stock. Only reference real products from the catalogue above.
2. If the user asks for a product not in the catalogue, set clarification_needed=false, intent='product_search', and explain politely in response_message that the store does not carry it.
3. If the user requests multiple products in one message, extract each one as a separate item in the 'items' list.
4. Extract quantities (e.g., 'two' -> 2, 'three' -> 3). Default quantity is 1 if unspecified.
5. Extract requested variants (e.g., size 'A4' or 'A5', color 'Black' or 'Blue', format 'Hardcover' or 'Paperback').
6. If a product requires a variant choice (e.g. A4 vs A5 notebook) and the customer did not specify, set clarification_needed=true, ask which variant they want in clarification_question, and explain in response_message.
7. If the customer mentions a budget (e.g. 'My budget is $50' or '₹1000' or 'under 30 dollars'), extract the numeric value into the 'budget' field.
8. Support intents: 'add_to_cart', 'modify_cart', 'remove_from_cart', 'product_search', 'product_recommendation', 'general_question', 'clarification', 'checkout'.
9. If the user wants to checkout, pay, or finalize their purchase (e.g., 'checkout', 'pay now', 'proceed to payment', 'proceed to checkout', 'ready to pay'), set intent='checkout'. The store has complete PayPal Checkout integration in the Shopping Cart tab. Never claim checkout or direct payment is unavailable.
10. Output STRICT JSON conforming to the requested schema.
"""

    @classmethod
    def call_gemini(
        cls,
        message: str,
        session_id: str,
        client_override: Any = None
    ) -> StructuredAIOutput:
        """
        Send customer message and conversational context to Gemini using the official SDK.
        Returns validated StructuredAIOutput.
        """
        # Fetch bounded conversation history
        history = ConversationService.get_history(session_id, limit=8)
        
        # Build prompt contents with conversational context
        prompt_parts = []
        if history:
            prompt_parts.append("CONVERSATION HISTORY:")
            for turn in history:
                role_label = "Customer" if turn["role"] == "user" else "CartPilot"
                prompt_parts.append(f"{role_label}: {turn['content']}")
            prompt_parts.append("\nCURRENT CUSTOMER MESSAGE:")
        
        prompt_parts.append(message)
        full_content = "\n".join(prompt_parts)

        # Obtain client (injected mock or live client)
        client = client_override or cls.get_gemini_client()

        try:
            from google.genai import types

            response = client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=full_content,
                config=types.GenerateContentConfig(
                    system_instruction=cls.generate_system_instruction(),
                    response_mime_type="application/json",
                    response_schema=StructuredAIOutput,
                    temperature=0.1
                )
            )

            # Extract raw response text
            raw_text = response.text if hasattr(response, "text") else str(response)
            if not raw_text:
                raise ValueError("Empty response received from Gemini model.")

            # Validate and parse with Pydantic
            data = json.loads(raw_text)
            return StructuredAIOutput(**data)

        except json.JSONDecodeError as jde:
            logger.error(f"Malformed JSON from Gemini: {jde}")
            return StructuredAIOutput(
                intent="clarification",
                items=[],
                clarification_needed=True,
                clarification_question="I could not fully process that request. Could you please specify which product you would like?",
                response_message="I'm having a little trouble understanding that request. Could you rephrase what you're looking for?"
            )
        except ValidationError as ve:
            logger.error(f"Schema validation error on AI output: {ve}")
            return StructuredAIOutput(
                intent="clarification",
                items=[],
                clarification_needed=True,
                clarification_question="Could you please clarify your shopping request?",
                response_message="Could you please provide a few more details on what you'd like to purchase?"
            )
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise

    @classmethod
    def process_shopping_message(
        cls,
        message: str,
        session_id: str,
        client_override: Any = None
    ) -> ChatResponse:
        """
        Orchestrate the full AI shopping pipeline with persistent cart integration:
        1. Contextual continuity check (handling follow-ups like 'A5' or 'Add one more')
        2. Gemini intent & entity extraction
        3. CatalogueService product resolution
        4. Variant validation
        5. Stock validation
        6. Backend price calculation
        7. Persistent cart synchronization in SQLite
        8. Budget verification
        9. Conversation history recording
        """
        # Retrieve active context
        context = ConversationService.get_context(session_id)
        last_product_id = context.get("last_discussed_product_id")
        saved_budget = context.get("current_budget")

        # 1. Check for direct checkout intent
        normalized_msg = message.strip().lower()
        checkout_keywords = [
            "checkout", "proceed to checkout", "proceed to payment", "pay now",
            "continue to pay", "ready to pay", "go to checkout", "pay", "buy now"
        ]
        is_direct_checkout = any(
            normalized_msg == kw or
            normalized_msg.startswith(kw + " ") or
            normalized_msg.endswith(" " + kw) or
            normalized_msg == f"i want to {kw}" or
            normalized_msg == f"i'd like to {kw}"
            for kw in checkout_keywords
        )

        if is_direct_checkout:
            current_cart = CartService.get_cart(session_id)
            cart_items = current_cart.get("items", []) if current_cart else []
            total_items = current_cart.get("total_items", 0) if current_cart else 0
            subtotal = current_cart.get("subtotal", 0.0) if current_cart else 0.0

            if not cart_items or total_items == 0:
                resp_msg = "Your shopping cart is currently empty! Please tell me what products you'd like to add before proceeding to checkout."
                suggestions = ["Show Stationery", "Show Books", "Gift Ideas under $30"]
            else:
                resp_msg = (
                    f"Your cart has {total_items} item{'s' if total_items > 1 else ''} "
                    f"totaling **${subtotal:.2f} USD**. You can complete your purchase anytime using the "
                    f"**PayPal** button located in your Shopping Cart on the right."
                )
                suggestions = ["Review Cart", "Add More Items", "Empty Cart"]

            ConversationService.add_message(session_id, "user", message)
            ConversationService.add_message(session_id, "assistant", resp_msg)
            cart_response = CartResponse(**current_cart) if current_cart else None

            return ChatResponse(
                session_id=session_id,
                message=resp_msg,
                intent="checkout",
                items=[],
                clarification_needed=False,
                budget=saved_budget,
                estimated_total=subtotal,
                suggestions=suggestions,
                cart=cart_response
            )

        # 2. Check if user is directly answering a previous clarification (e.g. "A5" or "Paperback")
        # or requesting incremental quantity (e.g. "Add one more")
        if last_product_id and (
            normalized_msg in ["a4", "a5", "black", "blue", "paperback", "hardcover", "silver", "matte black"] or
            normalized_msg.startswith("add one more") or
            normalized_msg.startswith("one more")
        ):
            product = CatalogueService.get_product_by_id(last_product_id)
            if product:
                if "more" in normalized_msg:
                    qty = 1
                    var = context.get("last_discussed_variant", {})
                else:
                    qty = 1
                    var = {"option": message.strip()}
                    
                resolved_var, err, is_clarif = CatalogueService.resolve_variants(product, var)
                has_stock, avail_stock = CatalogueService.check_stock(product["id"], qty)
                
                status = "available"
                warning = None
                if not has_stock:
                    status = "insufficient_stock"
                    warning = f"Only {avail_stock} items in stock."
                elif err and not is_clarif:
                    status = "variant_unavailable"
                    warning = err

                unit_price = round(float(product["price"]), 2)
                subtotal = round(unit_price * qty, 2)
                
                verified_item = VerifiedProductItem(
                    product_id=product["id"],
                    name=product["name"],
                    category=product["category"],
                    unit_price=unit_price,
                    quantity=qty,
                    variant=resolved_var,
                    subtotal=subtotal,
                    stock_available=avail_stock,
                    image_url=product["image_url"],
                    sku=product["sku"],
                    status=status,
                    warning=warning
                )

                # Persist to session cart if available
                updated_cart_data = None
                if status == "available" and not is_clarif:
                    try:
                        updated_cart_data = CartService.add_item(
                            session_id=session_id,
                            product_id=product["id"],
                            quantity=qty,
                            selected_variants=resolved_var
                        )
                    except Exception as ex:
                        logger.warning(f"Could not persist cart item: {ex}")

                resp_msg = f"Got it! I've updated your selection for {product['name']}."
                ConversationService.add_message(session_id, "user", message)
                ConversationService.add_message(session_id, "assistant", resp_msg)
                ConversationService.update_context(session_id, product_id=product["id"], variant=resolved_var)
                
                current_cart = CartService.get_cart(session_id)
                cart_response = CartResponse(**current_cart) if current_cart else None

                return ChatResponse(
                    session_id=session_id,
                    message=resp_msg,
                    intent="add_to_cart",
                    items=[verified_item],
                    clarification_needed=False,
                    budget=saved_budget,
                    estimated_total=subtotal,
                    suggestions=["View Cart", "Proceed to Checkout", "Continue Shopping"],
                    cart=cart_response
                )

        # 2. Call Gemini to extract structured intents
        ai_output = cls.call_gemini(message=message, session_id=session_id, client_override=client_override)

        # Update budget in session if customer specified one
        budget = ai_output.budget if ai_output.budget is not None else saved_budget
        if ai_output.budget is not None:
            ConversationService.update_context(session_id, budget=ai_output.budget)

        verified_items: List[VerifiedProductItem] = []
        clarification_needed = ai_output.clarification_needed
        clarification_question = ai_output.clarification_question
        response_message = ai_output.response_message

        # Handle checkout intent from AI model
        if ai_output.intent == "checkout":
            current_cart = CartService.get_cart(session_id)
            cart_items = current_cart.get("items", []) if current_cart else []
            total_items = current_cart.get("total_items", 0) if current_cart else 0
            subtotal = current_cart.get("subtotal", 0.0) if current_cart else 0.0

            if not cart_items or total_items == 0:
                response_message = "Your shopping cart is currently empty! Please tell me what products you'd like to add before proceeding to checkout."
                suggestions = ["Show Stationery", "Show Books", "Gift Ideas under $30"]
            else:
                response_message = (
                    f"Your cart has {total_items} item{'s' if total_items > 1 else ''} "
                    f"totaling **${subtotal:.2f} USD**. You can complete your purchase anytime using the "
                    f"**PayPal** button located in your Shopping Cart on the right."
                )
                suggestions = ["Review Cart", "Add More Items", "Empty Cart"]

            ConversationService.add_message(session_id, "user", message)
            ConversationService.add_message(session_id, "assistant", response_message)
            cart_response = CartResponse(**current_cart) if current_cart else None

            return ChatResponse(
                session_id=session_id,
                message=response_message,
                intent="checkout",
                items=[],
                clarification_needed=False,
                budget=saved_budget,
                estimated_total=subtotal,
                suggestions=suggestions,
                cart=cart_response
            )

        # 3. Ground every extracted item against CatalogueService
        for item in ai_output.items:
            matches = CatalogueService.match_product_query(item.product_query)
            
            # Scenario A: Product does not exist in store
            if not matches:
                verified_items.append(VerifiedProductItem(
                    product_id="unknown",
                    name=item.product_query,
                    category="Unknown",
                    unit_price=0.0,
                    quantity=item.quantity,
                    variant=item.variant,
                    subtotal=0.0,
                    stock_available=0,
                    image_url="",
                    sku="",
                    status="not_found",
                    warning=f"'{item.product_query}' is not available in our store catalogue."
                ))
                continue

            # Scenario B: Ambiguous product request (multiple distinct top matches)
            if len(matches) > 1 and (matches[0][1] - matches[1][1] < 0.15) and matches[0][1] < 0.95:
                clarification_needed = True
                matched_names = [m[0]["name"] for m in matches[:3]]
                clarification_question = f"Did you mean {', '.join(matched_names[:-1])} or {matched_names[-1]}?"
                response_message = f"I found a few similar items: {clarification_question}"
                
                # Still record potential candidates in status="ambiguous"
                for m, _ in matches[:2]:
                    verified_items.append(VerifiedProductItem(
                        product_id=m["id"],
                        name=m["name"],
                        category=m["category"],
                        unit_price=m["price"],
                        quantity=item.quantity,
                        variant={},
                        subtotal=round(m["price"] * item.quantity, 2),
                        stock_available=m["stock"],
                        image_url=m["image_url"],
                        sku=m["sku"],
                        status="ambiguous",
                        warning="Multiple matching products found. Please specify."
                    ))
                break

            # Scenario C: Single matched product
            product, score = matches[0]
            
            # Variant resolution
            resolved_variant, variant_err, is_missing_choice = CatalogueService.resolve_variants(
                product, item.variant
            )
            
            if is_missing_choice:
                clarification_needed = True
                clarification_question = variant_err
                response_message = variant_err
                ConversationService.update_context(
                    session_id,
                    product_id=product["id"],
                    clarification=clarification_question
                )

            # Stock check
            has_stock, available_stock = CatalogueService.check_stock(product["id"], item.quantity)
            
            status = "available"
            warning = None
            
            if not has_stock:
                status = "insufficient_stock"
                warning = f"Only {available_stock} items available in stock (requested {item.quantity})."
            elif variant_err and not is_missing_choice:
                status = "variant_unavailable"
                warning = variant_err

            # Grounded price calculation strictly from database
            grounded_unit_price = round(float(product["price"]), 2)
            subtotal = round(grounded_unit_price * item.quantity, 2)

            verified_items.append(VerifiedProductItem(
                product_id=product["id"],
                name=product["name"],
                category=product["category"],
                unit_price=grounded_unit_price,
                quantity=item.quantity,
                variant=resolved_variant,
                subtotal=subtotal,
                stock_available=available_stock,
                image_url=product["image_url"],
                sku=product["sku"],
                status=status,
                warning=warning
            ))
            
            # Store in context
            ConversationService.update_context(
                session_id,
                product_id=product["id"],
                variant=resolved_variant
            )

        # 4. If intent is add_to_cart and no clarification is needed, persist items to SQLite cart
        if ai_output.intent == "add_to_cart" and not clarification_needed:
            for v_item in verified_items:
                if v_item.status == "available":
                    try:
                        CartService.add_item(
                            session_id=session_id,
                            product_id=v_item.product_id,
                            quantity=v_item.quantity,
                            selected_variants=v_item.variant
                        )
                    except Exception as e:
                        logger.error(f"Failed to add verified item to persistent cart: {e}")

        # 5. Calculate total and verify budget
        estimated_total = round(sum(
            i.subtotal for i in verified_items if i.status == "available"
        ), 2)
        
        budget_exceeded = False
        budget_alert = None
        if budget is not None and estimated_total > budget:
            budget_exceeded = True
            budget_alert = f"Estimated total (${estimated_total:.2f}) exceeds your stated budget of ${budget:.2f}."

        # 6. Record message in conversation history
        ConversationService.add_message(session_id, "user", message)
        ConversationService.add_message(session_id, "assistant", response_message)

        # 7. Default interactive suggestions if model didn't provide any
        suggestions = ai_output.suggestions
        if not suggestions:
            if clarification_needed:
                suggestions = ["A4", "A5"] if "size" in str(clarification_question).lower() else ["Hardcover", "Paperback"]
            elif verified_items:
                suggestions = ["Add to Cart", "View Cart", "Checkout"]
            else:
                suggestions = ["Show Stationery", "Show Books", "Show Gift Ideas"]

        current_cart = CartService.get_cart(session_id)
        cart_response = CartResponse(**current_cart) if current_cart else None

        return ChatResponse(
            session_id=session_id,
            message=response_message,
            intent=ai_output.intent,
            items=verified_items,
            clarification_needed=clarification_needed,
            clarification_question=clarification_question,
            budget=budget,
            budget_exceeded=budget_exceeded,
            budget_alert=budget_alert,
            estimated_total=estimated_total,
            suggestions=suggestions,
            cart=cart_response
        )
