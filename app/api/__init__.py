# API routes
from app.api.restaurants import router as restaurants_router
from app.api.tables import router as tables_router
from app.api.waiters import router as waiters_router
from app.api.shifts import router as shifts_router
from app.api.waitlist import router as waitlist_router
from app.api.visits import router as visits_router
from app.api.routing import router as routing_router

__all__ = [
    "restaurants_router",
    "tables_router",
    "waiters_router",
    "shifts_router",
    "waitlist_router",
    "visits_router",
    "routing_router",
]
