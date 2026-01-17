# API routes
from app.api.restaurants import router as restaurants_router
from app.api.tables import router as tables_router
from app.api.waiters import router as waiters_router
from app.api.shifts import router as shifts_router
from app.api.waitlist import router as waitlist_router
from app.api.visits import router as visits_router
from app.api.routing import router as routing_router
from app.api.waiter_dashboard import router as waiter_dashboard_router
from app.api.scheduling import router as scheduling_router
from app.api.analytics import router as analytics_router
from app.api.menu_analytics import router as menu_analytics_router
from app.api.inventory import router as inventory_router
from app.api.kitchen_routing import router as kitchen_routing_router


__all__ = [
    "restaurants_router",
    "tables_router",
    "waiters_router",
    "shifts_router",
    "waitlist_router",
    "visits_router",
    "routing_router",
    "waiter_dashboard_router",
    "scheduling_router",
    "analytics_router",
    "menu_analytics_router",
    "inventory_router",
    "kitchen_routing_router",
]
