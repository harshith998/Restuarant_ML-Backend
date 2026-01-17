from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.menu import MenuItem, OrderItem
from app.models.visit import Visit

"""
Optimizes menu pricing based on demand and profitability.

Core algorithm logic:
reads menu items order items and aggregated sales data.

For each menu item:
1. Calculate demand_score = orders_per_day over last 30 days
2. Calculate profit_margin = (price - cost) / price
3. Calculate elasticity_factor = demand trend (increasing/decreasing)

Decision Matrix:
- High demand (>5 orders/day) + Low margin (<60%) → Increase price 10-15%
- High demand + High margin → Keep price (it's working)
- Low demand (<1 order/day) + Low margin → Decrease price 10% OR remove item
- Low demand + High margin → Decrease price 5-10% to increase volume

Output: List of price change recommendations with expected revenue impact
"""



class MenuOptimizationService:
    """Service for optimizing menu pricing based on demand and margins."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_pricing_recommendations(
        self, restaurant_id: UUID, lookback_days: int = 30
    ) -> List[Dict]:
        """
        Analyze menu items and recommend price adjustments.

        Returns list of recommendations with:
        - item_name, current_price, suggested_price, reason, expected_impact
        """
        cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)

        # Get all menu items with order counts
        stmt = (
            select(
                MenuItem.id,
                MenuItem.name,
                MenuItem.category,
                MenuItem.price,
                MenuItem.cost,
                func.count(OrderItem.id).label("times_ordered"),
            )
            .outerjoin(OrderItem, OrderItem.menu_item_id == MenuItem.id)
            .outerjoin(Visit, Visit.id == OrderItem.visit_id)
            .where(MenuItem.restaurant_id == restaurant_id)
            .where(MenuItem.is_available == True)
            .where(Visit.seated_at >= cutoff_date)
            .group_by(MenuItem.id)
        )

        result = await self.session.execute(stmt)
        items = result.all()

        recommendations = []
        for item in items:
            demand_score = item.times_ordered / lookback_days  # Orders per day
            
            if item.cost is None or item.price is None:
                continue

            margin = (float(item.price) - float(item.cost)) / float(item.price) if item.price > 0 else 0

            # Decision logic
            if demand_score > 5 and margin < 0.6:
                # High demand, low margin → Increase price
                new_price = round(float(item.price) * 1.12, 2)
                expected_revenue_gain = (new_price - float(item.price)) * item.times_ordered
                recommendations.append({
                    "item_id": str(item.id),
                    "item_name": item.name,
                    "category": item.category,
                    "current_price": float(item.price),
                    "current_cost": float(item.cost),
                    "suggested_price": float(new_price),
                    "reason": "High demand with low profit margin - increase price to improve profitability",
                    "current_margin": round(margin * 100, 1),
                    "new_margin": round(((new_price - float(item.cost)) / new_price) * 100, 1),
                    "demand_score": round(demand_score, 2),
                    "times_ordered": item.times_ordered,
                    "expected_revenue_impact": f"+${round(expected_revenue_gain, 2)}",
                    "action": "increase",
                })
            elif demand_score > 5 and margin >= 0.6:
                # High demand, good margin → Keep price
                recommendations.append({
                    "item_id": str(item.id),
                    "item_name": item.name,
                    "category": item.category,
                    "current_price": float(item.price),
                    "current_cost": float(item.cost),
                    "suggested_price": float(item.price),
                    "reason": "Strong performer - maintain current pricing",
                    "current_margin": round(margin * 100, 1),
                    "demand_score": round(demand_score, 2),
                    "times_ordered": item.times_ordered,
                    "action": "maintain",
                })
            elif demand_score < 1 and margin < 0.5:
                # Low demand, low margin → Consider removal
                recommendations.append({
                    "item_id": str(item.id),
                    "item_name": item.name,
                    "category": item.category,
                    "current_price": float(item.price),
                    "current_cost": float(item.cost),
                    "suggested_price": None,
                    "reason": "Poor seller with low profitability - consider removing from menu",
                    "current_margin": round(margin * 100, 1),
                    "demand_score": round(demand_score, 2),
                    "times_ordered": item.times_ordered,
                    "action": "remove",
                })
            elif demand_score < 2 and margin >= 0.5:
                # Low demand, good margin → Decrease price to boost volume
                new_price = round(float(item.price) * 0.90, 2)
                recommendations.append({
                    "item_id": str(item.id),
                    "item_name": item.name,
                    "category": item.category,
                    "current_price": float(item.price),
                    "current_cost": float(item.cost),
                    "suggested_price": float(new_price),
                    "reason": "Good margin but low sales - reduce price to increase volume",
                    "current_margin": round(margin * 100, 1),
                    "new_margin": round(((new_price - float(item.cost)) / new_price) * 100, 1),
                    "demand_score": round(demand_score, 2),
                    "times_ordered": item.times_ordered,
                    "action": "decrease",
                })

        return recommendations

    async def get_top_sellers(
        self, restaurant_id: UUID, period_days: int = 7, limit: int = 10
    ) -> List[Dict]:
        """Get top selling items by revenue and order count."""
        cutoff_date = datetime.utcnow() - timedelta(days=period_days)

        stmt = (
            select(
                MenuItem.id,
                MenuItem.name,
                MenuItem.category,
                MenuItem.price,
                func.count(OrderItem.id).label("times_ordered"),
                func.sum(OrderItem.total_price).label("total_revenue"),
            )
            .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
            .join(Visit, Visit.id == OrderItem.visit_id)
            .where(MenuItem.restaurant_id == restaurant_id)
            .where(Visit.seated_at >= cutoff_date)
            .group_by(MenuItem.id)
            .order_by(func.sum(OrderItem.total_price).desc())
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        items = result.all()

        return [
            {
                "item_id": str(item.id),
                "item_name": item.name,
                "category": item.category,
                "price": float(item.price) if item.price else 0,
                "times_ordered": item.times_ordered,
                "total_revenue": float(item.total_revenue) if item.total_revenue else 0,
            }
            for item in items
        ]
