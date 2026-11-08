from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.database.db import init_db
from app.routes.products import router as products_router
from app.routes.chat import router as chat_router
from app.routes.cart import router as cart_router
from app.routes.checkout import router as checkout_router
from app.routes.orders import router as orders_router
from app.routes.dashboard import router as dashboard_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database and seed sample catalogue
    init_db()
    yield
    # Shutdown logic if any

app = FastAPI(
    title="CartPilot AI",
    description="Conversational shopping assistant with PayPal checkout integration.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for local development and frontend client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(products_router)
app.include_router(chat_router)
app.include_router(cart_router)
app.include_router(checkout_router)
app.include_router(orders_router)
app.include_router(dashboard_router)

# Mount static directory if it exists
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def home():
    """Preserved home endpoint for health and status checking."""
    return {
        "message": "CartPilot AI is running!",
        "status": "success",
        "version": "1.0.0",
        "storefront_url": "/static/index.html",
        "dashboard_url": "/static/dashboard.html",
        "checkout_url": "/static/checkout.html",
        "docs_url": "/docs"
    }
