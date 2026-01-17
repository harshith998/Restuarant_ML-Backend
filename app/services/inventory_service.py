"""
Inventory planning and purchasing optimization service.

reads ingredients, recipis, order items, and menu items to make opitmized shopping list

For each ingredient:
1. Calculate usage per menu item:

   - Sum all recipes using this ingredient
   - Weight by menu item popularity (times ordered)

2. Calculate historical daily usage:
   - Total ingredient used = Σ(recipe.quantity × order_item.quantity) for last 30 days
   - Average daily usage = total / 30

3. Forecast future needs:
   - Projected usage (7 days) = avg_daily_usage × 7
   - Buffer stock = par_level - current_stock
   - Order quantity = max(projected_usage + buffer_stock, 0)

4. Cost optimization:
   - Group by supplier for bulk discounts
   - Flag overstocked items (current_stock > par_level × 1.5)

Output: Shopping list with quantities, costs, and supplier grouping
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingredient import Ingredient
from app.models.menu import MenuItem, OrderItem
from app.models.recipe import Recipe
from app.models.visit import Visit


class InventoryService:
    """Service for inventory management and purchasing recommendations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_shopping_list(
        self, restaurant_id: UUID, forecast_days: int = 7, lookback_days: int = 30
    ) -> Dict:
        """
        Generate shopping list based on historical usage and current stock.

        Returns dict with:
        - ingredients: list of items to order
        - total_cost: estimated purchase cost
        - by_supplier: grouped by supplier for bulk ordering
        """
        cutoff_date = datetime.utcnow() - timedelta(days=lookback_days)

        # Get all ingredients for restaurant
        ing_stmt = select(Ingredient).where(Ingredient.restaurant_id == restaurant_id)
        ing_result = await self.session.execute(ing_stmt)
        ingredients = ing_result.scalars().all()

        shopping_list = []
        total_cost = 0.0
        by_supplier = {}

        for ingredient in ingredients:
            # Calculate historical usage
            usage_stmt = (
                select(
                    func.sum(Recipe.quantity * OrderItem.quantity).label("total_used")
                )
                .join(MenuItem, MenuItem.id == Recipe.menu_item_id)
                .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
                .join(Visit, Visit.id == OrderItem.visit_id)
                .where(Recipe.ingredient_id == ingredient.id)
                .where(Visit.seated_at >= cutoff_date)
            )
            
            usage_result = await self.session.execute(usage_stmt)
            total_used = usage_result.scalar() or 0

            # Calculate metrics
            avg_daily_usage = float(total_used) / lookback_days if lookback_days > 0 else 0
            forecast_usage = avg_daily_usage * forecast_days
            buffer_needed = max(ingredient.par_level - float(ingredient.current_stock), 0)
            order_quantity = max(forecast_usage + buffer_needed, 0)

            # Only add to shopping list if we need to order
            if order_quantity > 0:
                item_cost = order_quantity * float(ingredient.cost_per_unit)
                total_cost += item_cost

                item_data = {
                    "ingredient_id": str(ingredient.id),
                    "name": ingredient.name,
                    "category": ingredient.category,
                    "unit": ingredient.unit,
                    "current_stock": float(ingredient.current_stock),
                    "par_level": ingredient.par_level,
                    "avg_daily_usage": round(avg_daily_usage, 2),
                    "forecast_usage": round(forecast_usage, 2),
                    "quantity_to_order": round(order_quantity, 2),
                    "cost_per_unit": float(ingredient.cost_per_unit),
                    "total_cost": round(item_cost, 2),
                    "supplier": ingredient.supplier,
                    "urgency": "high" if ingredient.current_stock < ingredient.par_level * 0.5 else "normal",
                }

                shopping_list.append(item_data)

                # Group by supplier
                if ingredient.supplier not in by_supplier:
                    by_supplier[ingredient.supplier] = {
                        "supplier_name": ingredient.supplier,
                        "items": [],
                        "total_cost": 0.0,
                    }
                by_supplier[ingredient.supplier]["items"].append(item_data)
                by_supplier[ingredient.supplier]["total_cost"] += item_cost

        return {
            "ingredients": shopping_list,
            "total_items": len(shopping_list),
            "total_cost": round(total_cost, 2),
            "forecast_period_days": forecast_days,
            "by_supplier": list(by_supplier.values()),
        }

    async def get_stock_alerts(self, restaurant_id: UUID) -> List[Dict]:
        """Get ingredients below par level."""
        stmt = (
            select(Ingredient)
            .where(Ingredient.restaurant_id == restaurant_id)
            .where(Ingredient.current_stock < Ingredient.par_level)
        )

        result = await self.session.execute(stmt)
        low_stock = result.scalars().all()

        return [
            {
                "ingredient_id": str(ing.id),
                "name": ing.name,
                "current_stock": float(ing.current_stock),
                "par_level": ing.par_level,
                "deficit": ing.par_level - float(ing.current_stock),
                "unit": ing.unit,
                "urgency": "critical" if ing.current_stock < ing.par_level * 0.3 else "warning",
            }
            for ing in low_stock
        ]
 