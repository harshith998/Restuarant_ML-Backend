from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import close_db, get_session_context, init_db
from app.services.seed_service import SeedService

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
    # Scheduling models
    StaffAvailability,
    StaffPreference,
    Schedule,
    ScheduleItem,
    ScheduleRun,
    ScheduleReasoning,
    StaffingRequirements,
    # Analytics models
    ScheduleInsights,
    Ingredient,
    Recipe,
    KitchenStation,
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

    # Auto-seed default data in development if DB is empty
    if settings.is_development:
        try:
            async with get_session_context() as session:
                seed_service = SeedService(session)
                result = await seed_service.ensure_default_data()
                if result.get("restaurants_created", 0) > 0:
                    LOGGER.info("Seeded default data: %s", result)
                else:
                    LOGGER.info("Default data already present; skipping seeding")
        except Exception as e:
            LOGGER.warning("Default data seeding failed: %s", e)

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

# Configure CORS (needed for browser preflight requests)
if settings.is_development:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
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
    chatbot_router,
    waiter_dashboard_router,
    scheduling_router,
    analytics_router,
)
from app.api.menu_analytics import router as menu_analytics_router
from app.api.inventory import router as inventory_router
from app.api.kitchen_routing import router as kitchen_routing_router

app.include_router(restaurants_router)
app.include_router(tables_router)
app.include_router(waiters_router)
app.include_router(shifts_router)
app.include_router(waitlist_router)
app.include_router(visits_router)
app.include_router(routing_router)
app.include_router(reviews_router)
app.include_router(chatbot_router)
app.include_router(waiter_dashboard_router)
app.include_router(scheduling_router)
app.include_router(analytics_router)
app.include_router(menu_analytics_router)
app.include_router(inventory_router)
app.include_router(kitchen_routing_router)

