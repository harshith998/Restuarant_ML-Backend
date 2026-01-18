"""
Menu item management service with ranking and 86 (availability) control.

Provides:
1. Menu item ranking by combined demand + margin score
2. 86 recommendations for low-performing items
3. Manual 86/un-86 actions
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.menu import MenuItem, OrderItem
from app.models.visit import Visit


class MenuService:
    """Service for menu item management and 86 operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_ranked_items(
        self,
        restaurant_id: UUID,
        lookback_days: int = 30,
        order: str = "desc",
        limit: int = 10,
        include_unavailable: bool = False,
    ) -> List[Dict]:
        """
        Get menu items ranked by combined demand + margin score.

        Score formula: (normalized_demand * 0.5) + (margin_pct * 0.5)
        - normalized_demand: orders_per_day scaled to 0-100
        - margin_pct: (price - cost) / price * 100

        Args:
            restaurant_id: Restaurant UUID
            lookback_days: Days to analyze for demand
            order: "desc" for highest scores first, "asc" for lowest first
            limit: Max items to return
            include_unavailable: Include 86'd items in results

        Returns:
            List of ranked items with scores and metrics
        """
        cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)

        # Build query for menu items with order counts
        stmt = (
            select(
                MenuItem.id,
                MenuItem.name,
                MenuItem.category,
                MenuItem.price,
                MenuItem.cost,
                MenuItem.is_available,
                func.coalesce(func.count(OrderItem.id), 0).label("times_ordered"),
            )
            .outerjoin(OrderItem, OrderItem.menu_item_id == MenuItem.id)
            .outerjoin(
                Visit,
                (Visit.id == OrderItem.visit_id) & (Visit.seated_at >= cutoff_date),
            )
            .where(MenuItem.restaurant_id == restaurant_id)
        )

        if not include_unavailable:
            stmt = stmt.where(MenuItem.is_available == True)

        stmt = stmt.group_by(MenuItem.id)

        result = await self.session.execute(stmt)
        items = result.all()

        if not items:
            return []

        # Calculate scores
        max_orders = max(item.times_ordered for item in items) or 1
        scored_items = []

        for item in items:
            if item.price is None or item.cost is None or item.price <= 0:
                continue

            orders_per_day = item.times_ordered / lookback_days
            normalized_demand = (item.times_ordered / max_orders) * 100
            margin_pct = ((float(item.price) - float(item.cost)) / float(item.price)) * 100
            combined_score = (normalized_demand * 0.5) + (margin_pct * 0.5)

            scored_items.append({
                "id": str(item.id),
                "name": item.name,
                "category": item.category,
                "price": float(item.price),
                "cost": float(item.cost),
                "is_available": item.is_available,
                "combined_score": round(combined_score, 2),
                "demand_score": round(normalized_demand, 2),
                "margin_pct": round(margin_pct, 2),
                "orders_per_day": round(orders_per_day, 2),
                "times_ordered": item.times_ordered,
            })

        # Sort by combined score
        scored_items.sort(
            key=lambda x: x["combined_score"],
            reverse=(order == "desc"),
        )

        # Add rank
        for i, item in enumerate(scored_items[:limit], 1):
            item["rank"] = i

        return scored_items[:limit]

    async def get_86_recommendations(
        self,
        restaurant_id: UUID,
        lookback_days: int = 30,
        score_threshold: float = 25.0,
    ) -> List[Dict]:
        """
        Get items recommended for 86 based on low performance scores.

        Returns available items scoring below the threshold.
        Does NOT auto-86 - just recommends.

        Args:
            restaurant_id: Restaurant UUID
            lookback_days: Days to analyze
            score_threshold: Items below this score are recommended

        Returns:
            List of items with reasons for 86 recommendation
        """
        # Get all ranked items (lowest first)
        all_items = await self.get_ranked_items(
            restaurant_id=restaurant_id,
            lookback_days=lookback_days,
            order="asc",
            limit=100,
            include_unavailable=False,
        )

        recommendations = []
        for item in all_items:
            if item["combined_score"] < score_threshold:
                # Generate reason based on metrics
                reasons = []
                if item["orders_per_day"] < 1:
                    reasons.append(f"Very low demand ({item['orders_per_day']} orders/day)")
                elif item["orders_per_day"] < 2:
                    reasons.append(f"Low demand ({item['orders_per_day']} orders/day)")

                if item["margin_pct"] < 50:
                    reasons.append(f"Low margin ({item['margin_pct']}%)")

                reason = " and ".join(reasons) if reasons else "Low combined score"

                recommendations.append({
                    "id": item["id"],
                    "name": item["name"],
                    "category": item["category"],
                    "price": item["price"],
                    "combined_score": item["combined_score"],
                    "demand_score": item["demand_score"],
                    "margin_pct": item["margin_pct"],
                    "orders_per_day": item["orders_per_day"],
                    "reason": reason,
                })

        return recommendations

    async def set_86_status(
        self,
        item_id: UUID,
        is_available: bool,
    ) -> Optional[MenuItem]:
        """
        Set the 86 status of a menu item.

        Args:
            item_id: Menu item UUID
            is_available: True to un-86, False to 86

        Returns:
            Updated MenuItem or None if not found
        """
        stmt = select(MenuItem).where(MenuItem.id == item_id)
        result = await self.session.execute(stmt)
        item = result.scalar_one_or_none()

        if not item:
            return None

        item.is_available = is_available
        item.updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(item)

        return item

    async def get_86d_items(
        self,
        restaurant_id: UUID,
    ) -> List[Dict]:
        """
        Get all currently 86'd items for a restaurant.

        Returns:
            List of unavailable menu items
        """
        stmt = (
            select(MenuItem)
            .where(MenuItem.restaurant_id == restaurant_id)
            .where(MenuItem.is_available == False)
            .order_by(MenuItem.updated_at.desc())
        )

        result = await self.session.execute(stmt)
        items = result.scalars().all()

        return [
            {
                "id": str(item.id),
                "name": item.name,
                "category": item.category,
                "price": float(item.price) if item.price else None,
                "is_available": item.is_available,
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            }
            for item in items
        ]

    async def get_item_by_id(
        self,
        item_id: UUID,
    ) -> Optional[MenuItem]:
        """Get a single menu item by ID."""
        stmt = select(MenuItem).where(MenuItem.id == item_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
