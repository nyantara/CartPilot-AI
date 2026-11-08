// CartPilot AI - Customer Front-end Application
// Integrates Gemini AI Shopping Assistant with Persistent SQLite Cart and PayPal Sandbox

let sessionId = "demo-session-001";
let currentCart = { items: [], subtotal: 0.0 };
let allProducts = [];
let paypalSdkLoaded = false;
let paypalButtonsInstance = null;
let isChatSubmitting = false;
let lastSubmittedText = "";
let lastSubmittedTimestamp = 0;

// Initialize on DOM Ready
document.addEventListener("DOMContentLoaded", () => {
    initSession();
    fetchCart();
    fetchCatalogue();
    initPayPalSDK();
    setupEventListeners();
});

// 1. Session Setup
function initSession() {
    const urlParams = new URLSearchParams(window.location.search);
    const querySess = urlParams.get("session_id");
    if (querySess) {
        sessionId = querySess;
    } else {
        const stored = localStorage.getItem("cartpilot_session_id");
        if (stored) sessionId = stored;
    }
    localStorage.setItem("cartpilot_session_id", sessionId);
    document.getElementById("sessionInput").value = sessionId;
}

function updateSession() {
    const newSess = document.getElementById("sessionInput").value.trim();
    if (newSess && newSess !== sessionId) {
        sessionId = newSess;
        localStorage.setItem("cartpilot_session_id", sessionId);
        fetchCart();
        appendSystemMessage(`Switched active shopping session to: <code>${escapeHtml(sessionId)}</code>`);
    }
}

function generateNewSession() {
    const rand = "sess_" + Math.random().toString(36).substring(2, 9);
    sessionId = rand;
    document.getElementById("sessionInput").value = sessionId;
    localStorage.setItem("cartpilot_session_id", sessionId);
    fetchCart();
    appendSystemMessage(`Started fresh shopping session: <code>${escapeHtml(sessionId)}</code>`);
}

// 2. Chat Assistant Handling
async function sendChatMessage(overrideText = null) {
    const inputEl = document.getElementById("chatInput");
    const message = (overrideText !== null ? overrideText : inputEl.value).trim();
    if (!message) return;

    // Prevent duplicate multi-click submissions or rapid identical queries
    const now = Date.now();
    if (isChatSubmitting) return;
    if (message.toLowerCase() === lastSubmittedText.toLowerCase() && (now - lastSubmittedTimestamp) < 1500) {
        return;
    }
    isChatSubmitting = true;
    lastSubmittedText = message;
    lastSubmittedTimestamp = now;

    if (overrideText === null) {
        inputEl.value = "";
    }

    // Append user bubble
    appendMessage("user", message);

    // Show AI loading bubble
    const loadingId = appendLoadingBubble();
    const sendBtn = document.getElementById("sendBtn");
    sendBtn.disabled = true;

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                session_id: sessionId,
                message: message
            })
        });

        removeBubble(loadingId);
        sendBtn.disabled = false;
        isChatSubmitting = false;

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            appendMessage("assistant", `⚠️ ${errData.detail || "Unable to reach shopping assistant. Please try again."}`);
            return;
        }

        const data = await res.json();
        renderAIResponse(data);

        // If items were added to cart by AI or cart returned in payload
        if (data.cart) {
            currentCart = data.cart;
            renderCartUI();
            if (paypalSdkLoaded) renderPayPalButtons();
        } else if (data.intent === "add_to_cart" || data.intent === "modify_cart" || data.intent === "remove_from_cart") {
            fetchCart();
        }

        // If checkout intent and cart has items, seamlessly switch to cart tab to reveal PayPal buttons
        if (data.intent === "checkout" && currentCart && currentCart.items && currentCart.items.length > 0) {
            switchTab("cart");
            setTimeout(() => {
                const ppCont = document.getElementById("cart-paypal-container");
                if (ppCont) {
                    ppCont.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            }, 100);
        }

    } catch (err) {
        removeBubble(loadingId);
        sendBtn.disabled = false;
        isChatSubmitting = false;
        appendMessage("assistant", `⚠️ Network error: ${err.message}`);
    }
}

function renderAIResponse(data) {
    const bubbleContent = document.createElement("div");
    
    // Main reply text with basic markdown formatting
    const rawText = data.message || data.reply || "";
    const formattedText = formatMarkdown(rawText);
    const textP = document.createElement("div");
    textP.innerHTML = formattedText;
    bubbleContent.appendChild(textP);

    // Budget alert banner
    if (data.budget_alert) {
        const budgetDiv = document.createElement("div");
        budgetDiv.style.marginTop = "0.5rem";
        budgetDiv.style.padding = "0.4rem 0.65rem";
        budgetDiv.style.background = "#fffbeb";
        budgetDiv.style.border = "1px solid #fde68a";
        budgetDiv.style.borderRadius = "6px";
        budgetDiv.style.fontSize = "0.8rem";
        budgetDiv.style.color = "#92400e";
        budgetDiv.style.fontWeight = "600";
        budgetDiv.textContent = `💡 ${data.budget_alert}`;
        bubbleContent.appendChild(budgetDiv);
    }

    // Clarification question
    if (data.clarification_question && !rawText.includes(data.clarification_question)) {
        const clarDiv = document.createElement("div");
        clarDiv.style.marginTop = "0.5rem";
        clarDiv.style.fontWeight = "600";
        clarDiv.style.color = "#0369a1";
        clarDiv.textContent = `❓ ${data.clarification_question}`;
        bubbleContent.appendChild(clarDiv);
    }

    // Grounded product cards
    const prods = data.items || data.products_referenced || [];
    if (prods.length > 0) {
        const grid = document.createElement("div");
        grid.className = "chat-products-grid";

        prods.forEach(prod => {
            const card = document.createElement("div");
            card.className = "chat-product-card";
            const pid = prod.product_id || prod.id;
            const price = prod.unit_price !== undefined ? prod.unit_price : prod.price;

            const imgHtml = prod.image_url 
                ? `<div class="card-img-wrap"><img src="${escapeHtml(prod.image_url)}" alt="${escapeHtml(prod.name)}" loading="lazy" /></div>` 
                : "";

            const variants = prod.variant || prod.variants || {};
            const varEntries = Object.entries(variants);
            let variantsHtml = "";
            if (varEntries.length > 0) {
                const pills = varEntries.map(([k, v]) => {
                    const text = Array.isArray(v) ? v.slice(0, 2).join(", ") : String(v);
                    return `<span class="var-pill">${escapeHtml(text)}</span>`;
                }).join("");
                variantsHtml = `<div class="card-variant-pills">${pills}</div>`;
            }

            const stockText = prod.stock_available !== undefined 
                ? `<span style="font-size:0.7rem; color:${prod.stock_available <= 20 ? '#ef4444' : '#10b981'}; font-weight:600;">${prod.stock_available} in stock</span>`
                : "";

            card.innerHTML = `
                ${imgHtml}
                <div class="card-prod-title">${escapeHtml(prod.name)}</div>
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span class="card-prod-price">$${Number(price).toFixed(2)}</span>
                    ${stockText}
                </div>
                ${variantsHtml}
                <button class="btn-card-add" onclick="quickAddToCart('${pid}', '${escapeHtml(prod.name)}')">
                    <span>🛒</span> Add to Cart
                </button>
            `;
            grid.appendChild(card);
        });

        bubbleContent.appendChild(grid);
    }

    // Quick-reply suggestions chips
    if (data.suggestions && data.suggestions.length > 0) {
        const sugWrap = document.createElement("div");
        sugWrap.style.display = "flex";
        sugWrap.style.flexWrap = "wrap";
        sugWrap.style.gap = "0.35rem";
        sugWrap.style.marginTop = "0.75rem";

        data.suggestions.forEach(sug => {
            const btn = document.createElement("button");
            btn.className = "suggestion-chip";
            btn.style.fontSize = "0.75rem";
            btn.textContent = `💬 ${sug}`;
            btn.onclick = () => sendChatMessage(sug);
            sugWrap.appendChild(btn);
        });

        bubbleContent.appendChild(sugWrap);
    }

    appendCustomAssistantBubble(bubbleContent);
}

function appendMessage(role, text) {
    const list = document.getElementById("chatMessages");
    const row = document.createElement("div");
    row.className = `message-row ${role}`;

    const avatar = document.createElement("div");
    avatar.className = `msg-avatar ${role === "user" ? "user-av" : "ai-av"}`;
    avatar.textContent = role === "user" ? "👤" : "🤖";

    const body = document.createElement("div");
    body.className = "msg-body";

    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";
    bubble.innerHTML = role === "user" ? `<p>${escapeHtml(text)}</p>` : formatMarkdown(text);

    body.appendChild(bubble);
    row.appendChild(avatar);
    row.appendChild(body);
    list.appendChild(row);

    list.scrollTop = list.scrollHeight;
    return row;
}

function appendCustomAssistantBubble(contentNode) {
    const list = document.getElementById("chatMessages");
    const row = document.createElement("div");
    row.className = "message-row assistant";

    const avatar = document.createElement("div");
    avatar.className = "msg-avatar ai-av";
    avatar.textContent = "🤖";

    const body = document.createElement("div");
    body.className = "msg-body";

    const bubble = document.createElement("div");
    bubble.className = "msg-bubble";
    bubble.appendChild(contentNode);

    body.appendChild(bubble);
    row.appendChild(avatar);
    row.appendChild(body);
    list.appendChild(row);

    list.scrollTop = list.scrollHeight;
}

function appendSystemMessage(htmlText) {
    const list = document.getElementById("chatMessages");
    const div = document.createElement("div");
    div.style.textAlign = "center";
    div.style.fontSize = "0.75rem";
    div.style.color = "#64748b";
    div.style.margin = "0.5rem 0";
    div.innerHTML = htmlText;
    list.appendChild(div);
    list.scrollTop = list.scrollHeight;
}

function appendLoadingBubble() {
    const id = "loading-" + Date.now();
    const list = document.getElementById("chatMessages");
    const row = document.createElement("div");
    row.id = id;
    row.className = "message-row assistant";
    row.innerHTML = `
        <div class="msg-avatar ai-av">🤖</div>
        <div class="msg-body">
            <div class="msg-bubble" style="display:flex; align-items:center; gap:0.4rem; color:#64748b;">
                <span>CartPilot is checking catalogue & pricing</span>
                <span class="ai-pulse" style="animation: pulse 1s infinite;"></span>
            </div>
        </div>
    `;
    list.appendChild(row);
    list.scrollTop = list.scrollHeight;
    return id;
}

function removeBubble(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

// 3. Cart Management
async function fetchCart() {
    try {
        const res = await fetch(`/api/cart/${sessionId}`);
        if (!res.ok) throw new Error("Failed to load cart");
        currentCart = await res.json();
        renderCartUI();
        if (paypalSdkLoaded) {
            renderPayPalButtons();
        }
    } catch (err) {
        console.error("Cart error:", err);
    }
}

function renderCartUI() {
    const container = document.getElementById("cartItemsList");
    const countBadge = document.getElementById("navCartCount");
    const totalCount = (currentCart.items || []).reduce((sum, itm) => sum + itm.quantity, 0);

    // Update navbar badge
    countBadge.textContent = totalCount;

    // Render items or empty view
    if (!currentCart.items || currentCart.items.length === 0) {
        container.innerHTML = `
            <div class="empty-cart-view">
                <div class="empty-icon">🛒</div>
                <div style="font-weight: 600; color: #334155;">Your cart is empty</div>
                <div style="font-size: 0.8rem;">Ask CartPilot to find items or browse the Catalogue tab.</div>
            </div>
        `;
        document.getElementById("cartSubtotal").textContent = "$0.00";
        document.getElementById("cartTotal").textContent = "$0.00";
        document.getElementById("cartSummaryBlock").style.display = "none";
        document.getElementById("cart-paypal-container").style.display = "none";
        return;
    }

    document.getElementById("cartSummaryBlock").style.display = "block";
    document.getElementById("cart-paypal-container").style.display = "block";

    container.innerHTML = currentCart.items.map(item => {
        const varStr = item.selected_variants && Object.keys(item.selected_variants).length > 0
            ? Object.entries(item.selected_variants).map(([k, v]) => `${v}`).join(", ")
            : "";

        return `
            <div class="cart-item-card">
                <div class="cart-item-info">
                    <div class="cart-item-name">${escapeHtml(item.product_name)}</div>
                    <div class="cart-item-meta">
                        $${item.unit_price.toFixed(2)} each ${varStr ? `• <span style="color:#0284c7;">${escapeHtml(varStr)}</span>` : ''}
                    </div>
                </div>
                <div class="cart-qty-ctrls">
                    <button class="btn-qty" onclick="changeItemQty('${item.id}', ${item.quantity - 1})">-</button>
                    <span class="qty-val">${item.quantity}</span>
                    <button class="btn-qty" onclick="changeItemQty('${item.id}', ${item.quantity + 1})">+</button>
                </div>
                <div class="cart-item-subtotal">$${item.subtotal.toFixed(2)}</div>
                <button class="btn-del-item" onclick="deleteCartItem('${item.id}')" title="Remove item">✕</button>
            </div>
        `;
    }).join("");

    document.getElementById("cartSubtotal").textContent = `$${currentCart.subtotal.toFixed(2)}`;
    document.getElementById("cartTotal").textContent = `$${currentCart.subtotal.toFixed(2)}`;
}

async function quickAddToCart(productId, productName) {
    try {
        const res = await fetch(`/api/cart/${sessionId}/items`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                product_id: productId,
                quantity: 1,
                selected_variants: {}
            })
        });

        if (!res.ok) {
            const err = await res.json();
            alert(`Could not add to cart: ${err.detail}`);
            return;
        }

        await fetchCart();
        switchTab("cart");
        appendSystemMessage(`Added 1x <strong>${escapeHtml(productName)}</strong> to cart.`);
    } catch (err) {
        console.error("Quick add error:", err);
    }
}

async function changeItemQty(itemId, newQty) {
    if (newQty <= 0) {
        return deleteCartItem(itemId);
    }

    try {
        const res = await fetch(`/api/cart/${sessionId}/items/${itemId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ quantity: newQty })
        });
        if (!res.ok) {
            const err = await res.json();
            alert(`Failed to update quantity: ${err.detail}`);
            return;
        }
        fetchCart();
    } catch (err) {
        console.error("Update qty error:", err);
    }
}

async function deleteCartItem(itemId) {
    try {
        await fetch(`/api/cart/${sessionId}/items/${itemId}`, { method: "DELETE" });
        fetchCart();
    } catch (err) {
        console.error("Delete item error:", err);
    }
}

async function clearEntireCart() {
    if (!confirm("Are you sure you want to empty your cart?")) return;
    try {
        await fetch(`/api/cart/${sessionId}`, { method: "DELETE" });
        fetchCart();
    } catch (err) {
        console.error("Clear cart error:", err);
    }
}

// 4. Product Catalogue Browser
async function fetchCatalogue() {
    try {
        const res = await fetch("/api/products");
        if (!res.ok) throw new Error("Failed to load products");
        allProducts = await res.json();
        renderCatalogue("ALL");
    } catch (err) {
        console.error("Catalogue error:", err);
    }
}

function renderCatalogue(category = "ALL") {
    const grid = document.getElementById("catalogueGrid");
    const filtered = category === "ALL" 
        ? allProducts 
        : allProducts.filter(p => p.category.toLowerCase() === category.toLowerCase());

    if (!filtered || filtered.length === 0) {
        grid.innerHTML = `<div style="grid-column: 1/-1; padding: 2rem; text-align: center; color: #64748b;">No products found in this category.</div>`;
        return;
    }

    grid.innerHTML = filtered.map(prod => `
        <div class="catalogue-card">
            <div class="card-img-wrap">
                <img src="${escapeHtml(prod.image_url)}" alt="${escapeHtml(prod.name)}" loading="lazy" />
            </div>
            <div style="font-size: 0.725rem; color: #64748b; font-weight: 600;">${escapeHtml(prod.category)}</div>
            <div class="card-prod-title">${escapeHtml(prod.name)}</div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: auto;">
                <span class="card-prod-price">$${prod.price.toFixed(2)}</span>
                <span style="font-size: 0.725rem; color: ${prod.stock <= 20 ? '#ef4444' : '#10b981'}; font-weight: 600;">
                    ${prod.stock} in stock
                </span>
            </div>
            <div style="display: flex; gap: 0.35rem; margin-top: 0.4rem;">
                <button class="btn-card-add" style="flex: 1;" onclick="quickAddToCart('${prod.id}', '${escapeHtml(prod.name)}')">
                    + Add
                </button>
                <button class="btn-card-add" style="background: #f1f5f9; color: #334155; border: 1px solid #cbd5e1;" onclick="askAiAboutProduct('${escapeHtml(prod.name)}')">
                    Ask AI
                </button>
            </div>
        </div>
    `).join("");
}

function askAiAboutProduct(productName) {
    sendChatMessage(`Tell me more about the ${productName} and check if it's available.`);
}

// 5. PayPal Checkout Integration
async function initPayPalSDK() {
    try {
        const configRes = await fetch("/api/checkout/config");
        const config = await configRes.json();
        const clientId = config.client_id || "sb";

        const script = document.createElement("script");
        script.src = `https://www.paypal.com/sdk/js?client-id=${clientId}&currency=USD&intent=capture&components=buttons`;
        script.onload = () => {
            paypalSdkLoaded = true;
            renderPayPalButtons();
        };
        document.head.appendChild(script);
    } catch (err) {
        console.error("PayPal SDK init error:", err);
    }
}

function renderPayPalButtons() {
    if (typeof paypal === "undefined" || !currentCart || currentCart.subtotal <= 0) {
        return;
    }

    const container = document.getElementById("cart-paypal-container");
    container.innerHTML = "";

    paypal.Buttons({
        style: {
            layout: 'vertical',
            color: 'gold',
            shape: 'rect',
            label: 'paypal'
        },

        createOrder: async (data, actions) => {
            if (!currentCart || currentCart.subtotal <= 0) {
                alert("Cart is empty. Please add items before checking out.");
                throw new Error("Empty cart");
            }

            const res = await fetch("/api/checkout/create-order", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    session_id: sessionId,
                    customer_name: "CartPilot Shopper",
                    customer_email: "shopper@sandbox.paypal.com"
                })
            });

            const orderData = await res.json();
            if (!res.ok) {
                alert(`Order creation failed: ${orderData.detail}`);
                throw new Error(orderData.detail);
            }

            return orderData.paypal_order_id;
        },

        onApprove: async (data, actions) => {
            appendSystemMessage("Verifying and capturing payment with PayPal backend...");

            try {
                const res = await fetch(`/api/checkout/capture-order/${data.orderID}`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ session_id: sessionId })
                });

                const captureData = await res.json();
                if (!res.ok) {
                    throw new Error(captureData.detail || "Capture failed");
                }

                // Show success modal
                showSuccessModal(captureData);
                // Refresh cart
                fetchCart();

            } catch (err) {
                alert(`Payment capture error: ${err.message}`);
            }
        },

        onCancel: async (data) => {
            appendSystemMessage("PayPal checkout cancelled. Items were preserved in your cart.");
            if (data && data.orderID) {
                fetch(`/api/checkout/cancel-order/${data.orderID}`, { method: "POST" });
            }
        },

        onError: (err) => {
            console.error("PayPal Error:", err);
            alert("PayPal Popup Note: Please make sure you sign into the PayPal modal using a Personal Sandbox Buyer account (not the merchant email) and disable popup blockers.");
        }
    }).render('#cart-paypal-container');
}

function showSuccessModal(data) {
    document.getElementById("modalOrderId").textContent = data.order_id;
    document.getElementById("modalCaptureId").textContent = data.capture_id || "N/A";
    document.getElementById("modalAmount").textContent = `$${data.amount_captured.toFixed(2)} ${data.currency}`;
    document.getElementById("modalPayer").textContent = data.customer_name || "Buyer";
    document.getElementById("successModal").classList.add("open");
}

function closeSuccessModal() {
    document.getElementById("successModal").classList.remove("open");
}

// 6. UI Helpers & Event Listeners
function setupEventListeners() {
    // Send message on Enter
    document.getElementById("chatInput").addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            sendChatMessage();
        }
    });

    document.getElementById("sendBtn").addEventListener("click", () => {
        sendChatMessage();
    });

    // Session controls
    document.getElementById("sessionInput").addEventListener("change", updateSession);
    document.getElementById("newSessionBtn").addEventListener("click", generateNewSession);

    // Nav cart toggle
    document.getElementById("navCartBtn").addEventListener("click", () => {
        switchTab("cart");
    });

    // Clear cart button
    document.getElementById("clearCartBtn").addEventListener("click", clearEntireCart);

    // Tab buttons
    document.querySelectorAll(".tab-btn").forEach(btn => {
        btn.addEventListener("click", (e) => {
            const targetTab = e.currentTarget.getAttribute("data-tab");
            switchTab(targetTab);
        });
    });

    // Catalogue category filter pills
    document.querySelectorAll(".cat-pill").forEach(pill => {
        pill.addEventListener("click", (e) => {
            document.querySelectorAll(".cat-pill").forEach(p => p.classList.remove("active"));
            e.currentTarget.classList.add("active");
            const cat = e.currentTarget.getAttribute("data-cat");
            renderCatalogue(cat);
        });
    });

    // Suggestion chips
    document.querySelectorAll(".suggestion-chip").forEach(chip => {
        chip.addEventListener("click", (e) => {
            const prompt = e.currentTarget.textContent.trim().replace(/^[^\w\s]+/, '').trim();
            sendChatMessage(prompt);
        });
    });

    // Close success modal
    document.getElementById("modalCloseBtn").addEventListener("click", closeSuccessModal);
}

function switchTab(tabName) {
    document.querySelectorAll(".tab-btn").forEach(b => {
        b.classList.toggle("active", b.getAttribute("data-tab") === tabName);
    });
    document.getElementById("cartTabContent").classList.toggle("active", tabName === "cart");
    document.getElementById("catalogueTabContent").classList.toggle("active", tabName === "catalogue");
}

function formatMarkdown(text) {
    if (!text) return "";
    let html = escapeHtml(text);
    // Bold
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Italic
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    // Bullet lists
    html = html.replace(/^\s*[-*]\s+(.*)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
    // Line breaks
    html = html.replace(/\n\n/g, '<br/><br/>');
    html = html.replace(/\n/g, '<br/>');
    return html;
}

function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}
