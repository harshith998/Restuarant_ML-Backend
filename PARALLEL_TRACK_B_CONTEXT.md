# Track B: Context Assembly (Terminal 2)

**Estimated Time:** 4-5 hours
**Dependencies:** Existing database models only
**Owner:** Assign to Terminal/Developer 2

---

## Overview

Build the context assembly service that queries existing database models to gather restaurant data for the chatbot. This can be developed independently and tested against the existing database.

---

## Hour-by-Hour Tasks

### Hour 1: Setup & Review Data Fetching

**Tasks:**
1. Create new file: `app/services/chatbot_context.py`

2. Add imports and review data function:
   ```python
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
               "category_opinions": review_summary.category_opinions,
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

       # Placeholder for other data sources
       menu_data = {"top_items": []}
       staff_data = {"total_staff": 0, "top_performer": "N/A", "top_tier": "N/A"}
       revenue_data = {"today_revenue": 0.0, "today_covers": 0}
       scheduling_data = {"active_shifts": 0}

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
   ```

**Deliverable:** Basic structure with review data working

---

### Hour 2: Menu Data Query

**Tasks:**
1. Add menu query to `assemble_restaurant_context()` (replace placeholder):
   ```python
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
   ```

**Deliverable:** Menu data query integrated

---

### Hour 3: Staff Data Query

**Tasks:**
1. Add staff query to `assemble_restaurant_context()`:
   ```python
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
   ```

**Deliverable:** Staff data query integrated

---

### Hour 4: Revenue & Scheduling Queries

**Tasks:**
1. Add revenue query:
   ```python
   # 4. Revenue data (today's sales)
   from app.models.visit import Visit

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
   ```

2. Add scheduling query:
   ```python
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
   ```

**Deliverable:** Complete context assembly function

---

### Hour 5: Testing

**Tasks:**
1. Create test script `test_context_manual.py`:
   ```python
   """Manual test for context assembly."""
   import asyncio
   from uuid import UUID
   from app.database import get_session
   from app.services.chatbot_context import assemble_restaurant_context

   async def test_context():
       # Replace with actual restaurant ID from your database
       restaurant_id = UUID("REPLACE-WITH-REAL-UUID")

       async for session in get_session():
           context = await assemble_restaurant_context(restaurant_id, session)

           print("Restaurant Context:")
           print("=" * 60)
           print(f"\nRestaurant ID: {context['restaurant_info']['id']}")

           print("\n📊 Review Insights:")
           print(f"  - Average: {context['review_insights']['overall_average']} stars")
           print(f"  - Total: {context['review_insights']['total_reviews']} reviews")
           print(f"  - Needs attention: {context['review_insights']['needs_attention']}")

           print("\n🍽️  Menu Performance:")
           print(f"  - Top items: {len(context['menu_performance']['top_items'])}")
           for item in context['menu_performance']['top_items'][:3]:
               print(f"    • {item['name']} ({item['orders']} orders)")

           print("\n👥 Staff Performance:")
           print(f"  - Total staff: {context['staff_performance']['total_staff']}")
           print(f"  - Top performer: {context['staff_performance']['top_performer']}")
           print(f"  - Tier: {context['staff_performance']['top_tier']}")

           print("\n💰 Revenue Metrics:")
           print(f"  - Today: ${context['revenue_metrics']['today_revenue']:.2f}")
           print(f"  - Covers: {context['revenue_metrics']['today_covers']}")

           print("\n📅 Scheduling:")
           print(f"  - Active shifts: {context['scheduling_info']['active_shifts']}")

           break

   if __name__ == "__main__":
       asyncio.run(test_context())
   ```

2. Run test:
   ```bash
   python test_context_manual.py
   ```

3. Verify all data sources return values (even if 0)

**Deliverable:** Tested and working context assembly

---

## Completion Checklist

- [ ] `app/services/chatbot_context.py` created
- [ ] Review data fetching works
- [ ] Menu data query works
- [ ] Staff data query works
- [ ] Revenue data query works
- [ ] Scheduling data query works
- [ ] Manual test passes with real restaurant ID
- [ ] Graceful error handling for missing data

---

## Handoff to Track C

**Files to provide:**
- `app/services/chatbot_context.py` - Complete and tested

**Functions available:**
- `assemble_restaurant_context(restaurant_id: UUID, session: AsyncSession) -> dict`

**Returns structure:**
```python
{
    "restaurant_info": {"id": str, "name": str},
    "review_insights": {...},
    "menu_performance": {...},
    "staff_performance": {...},
    "revenue_metrics": {...},
    "scheduling_info": {...}
}
```

---

## Troubleshooting

**Issue:** `AttributeError: 'NoneType' object has no attribute 'overall_average'`
- **Fix:** Add try/except around each data source (already in code above)

**Issue:** No menu items returned
- **Fix:** Check if restaurant has visits with order_items in last 30 days

**Issue:** Database connection fails
- **Fix:** Ensure database is running: `docker-compose up -d db`

**Issue:** Restaurant ID not found
- **Fix:** Query database for valid restaurant UUID:
  ```sql
  SELECT id FROM restaurants LIMIT 1;
  ```
