"""Restaurant context assembly for chatbot."""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def assemble_restaurant_context(
    restaurant_id: UUID, session: AsyncSession
) -> dict:
    """
    Assemble complete restaurant context for chatbot.

    Args:
        restaurant_id: Restaurant UUID
        session: Database session

    Returns:
        Dictionary with all restaurant data
    """
    # 1. Review data (use existing services)
    from app.services.review_stats import get_review_stats
    from app.services.review_summary import get_aggregate_summary

    try:
        review_stats = await get_review_stats(restaurant_id, session)
        review_summary = await get_aggregate_summary(restaurant_id, session)

        review_data = {
            "overall_average": review_stats.overall_average,
            "total_reviews": review_stats.total_reviews,
            "category_opinions": review_summary.category_opinions.model_dump(),
            "needs_attention": review_summary.needs_attention,
        }
    except Exception as e:
        # Graceful fallback if no reviews
        review_data = {
            "overall_average": 0.0,
            "total_reviews": 0,
            "category_opinions": {},
            "needs_attention": False,
        }

    # 2. Menu data (top 5 items by recent orders)
    from app.models.menu import MenuItem, OrderItem
    from app.models.visit import Visit

    menu_query = (
        select(
            MenuItem.name,
            MenuItem.price,
            func.count(OrderItem.id).label("order_count"),
        )
        .join(OrderItem, MenuItem.id == OrderItem.menu_item_id)
        .join(Visit, OrderItem.visit_id == Visit.id)
        .where(MenuItem.restaurant_id == restaurant_id)
        .where(Visit.payment_at >= datetime.now() - timedelta(days=30))
        .group_by(MenuItem.id, MenuItem.name, MenuItem.price)
        .order_by(func.count(OrderItem.id).desc())
        .limit(5)
    )

    try:
        top_menu_result = await session.execute(menu_query)
        top_menu_items = [
            {"name": row.name, "price": float(row.price), "orders": row.order_count}
            for row in top_menu_result
        ]
    except Exception:
        top_menu_items = []

    menu_data = {
        "top_items": top_menu_items,
        "total_active_items": len(top_menu_items),  # Simplified
    }

    # 3. Staff data (active waiters with tier)
    from app.models.waiter import Waiter

    staff_query = (
        select(Waiter)
        .where(Waiter.restaurant_id == restaurant_id, Waiter.is_active == True)
        .order_by(Waiter.composite_score.desc())
    )

    try:
        staff_result = await session.execute(staff_query)
        waiters = staff_result.scalars().all()

        staff_data = {
            "total_staff": len(waiters),
            "top_performer": waiters[0].name if waiters else "No staff",
            "top_tier": waiters[0].tier if waiters else "N/A",
            "avg_efficiency": (
                sum(w.composite_score for w in waiters) / len(waiters)
                if waiters
                else 0.0
            ),
        }
    except Exception:
        staff_data = {
            "total_staff": 0,
            "top_performer": "N/A",
            "top_tier": "N/A",
            "avg_efficiency": 0.0,
        }

    # 4. Revenue data (today's sales)
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    revenue_query = (
        select(
            func.sum(Visit.total).label("revenue"),
            func.count(Visit.id).label("covers"),
        )
        .where(Visit.restaurant_id == restaurant_id)
        .where(Visit.payment_at >= today_start)
    )

    try:
        revenue_result = await session.execute(revenue_query)
        revenue_row = revenue_result.first()

        revenue_data = {
            "today_revenue": float(revenue_row.revenue or 0),
            "today_covers": revenue_row.covers or 0,
            "average_check": (
                float(revenue_row.revenue / revenue_row.covers)
                if revenue_row.covers
                else 0.0
            ),
        }
    except Exception:
        revenue_data = {
            "today_revenue": 0.0,
            "today_covers": 0,
            "average_check": 0.0,
        }

    # 5. Scheduling data (active shifts)
    from app.models.shift import Shift

    shifts_query = (
        select(func.count(Shift.id))
        .where(Shift.restaurant_id == restaurant_id, Shift.status == "active")
    )

    try:
        active_shifts_result = await session.execute(shifts_query)
        active_shifts = active_shifts_result.scalar() or 0
    except Exception:
        active_shifts = 0

    scheduling_data = {"active_shifts": active_shifts}

    return {
        "restaurant_info": {
            "id": str(restaurant_id),
            "name": "Restaurant"  # Can query Restaurant model if needed
        },
        "review_insights": review_data,
        "menu_performance": menu_data,
        "staff_performance": staff_data,
        "revenue_metrics": revenue_data,
        "scheduling_info": scheduling_data,
    }
