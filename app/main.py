"""
Restaurant Intelligence Platform - FastAPI Application

Main entry point for the API server.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import close_db, init_db

# Import all models to register them with Base BEFORE init_db
# This ensures create_all() sees all tables
from app.models import (  # noqa: F401
    Restaurant,
    Section,
    Table,
    Waiter,
    Shift,
    WaitlistEntry,
    Visit,
    MenuItem,
    OrderItem,
    WaiterMetrics,
    RestaurantMetrics,
    MenuItemMetrics,
    TableStateLog,
    CameraSource,
    CameraCropState,
    CropDispatchLog,
    Review,
)

# ML services (optional - only load if ML is enabled)
ML_ENABLED = os.getenv("ML_ENABLED", "false").lower() == "true"

settings = get_settings()
LOGGER = logging.getLogger("restaurant-platform")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown events."""
    # Startup - always create tables if they don't exist
    # This is safe because create_all() is idempotent
    try:
        await init_db()
        LOGGER.info("Database initialized")
    except Exception as e:
        LOGGER.error("Database initialization failed: %s", e)
        raise

    # Initialize ML services if enabled
    if ML_ENABLED:
        try:
            from app.ml.classifier_api import init_model
            from app.ml.crop_api import init_service

            init_model()
            service = init_service()
            await service.start()
            LOGGER.info("ML services initialized")
        except Exception as e:
            LOGGER.warning("ML services failed to initialize: %s", e)

    yield

    # Shutdown
    if ML_ENABLED:
        try:
            from app.ml.crop_api import get_service
            service = get_service()
            await service.stop()
        except Exception:
            pass

    await close_db()


app = FastAPI(
    title="Restaurant Intelligence Platform",
    description="PostgreSQL-backed data layer and routing API for restaurant operations",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "service": "restaurant-intelligence-platform"}


@app.get("/")
async def root() -> dict:
    """Root endpoint with API information."""
    return {
        "name": "Restaurant Intelligence Platform",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/healthz",
    }


# Include ML routers if enabled
if ML_ENABLED:
    from app.ml.classifier_api import router as ml_router
    from app.ml.crop_api import router as crop_router
    app.include_router(ml_router)
    app.include_router(crop_router)

# Include API routers
from app.api import (
    restaurants_router,
    tables_router,
    waiters_router,
    shifts_router,
    waitlist_router,
    visits_router,
    routing_router,
    reviews_router,
)

app.include_router(restaurants_router)
app.include_router(tables_router)
app.include_router(waiters_router)
app.include_router(shifts_router)
app.include_router(waitlist_router)
app.include_router(visits_router)
app.include_router(routing_router)
app.include_router(reviews_router)
